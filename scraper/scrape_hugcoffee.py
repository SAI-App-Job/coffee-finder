# -*- coding: utf-8 -*-
"""
scrape_hugcoffee.py

hugcoffee(ハグコーヒー、shop.hugcoffee.co、静岡県静岡市葵区西門町5-3のロースタリー。
1号店は両替町1-3-9)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点、products.json全83商品): product_typeが「COFFEE」の
商品のうち、焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とする。ドリップバッグ・
セット・フリーズドライ・リキッド・カフェオレベース等は除外。

【重量について】
実データ確認済み: 同一銘柄が「<銘柄>｜100g/200g/1kg」の重量違いの別商品として並ぶため、
銘柄ごとに最小重量の商品を代表とする(100gは2銘柄のみで、他は200gが最小)。各商品の
バリエーションは挽き方(豆のまま/ペーパーフィルター用/フレンチプレス用等)で価格は同一。
「豆のまま」のバリエーションを代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    detect_processing_method,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "hugcoffee",
    "url": "https://shop.hugcoffee.co/",
    "platform": "Shopify",
    "address": "静岡県静岡市葵区西門町5-3",
    "prefecture": "静岡県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.hugcoffee.co"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# --- 共通ヘルパー(焙煎度・ラベル付き説明文の解析) -----------------------------
ROAST_JP_PATTERN = re.compile(r"(極深|中深|中浅|深|中|浅)\s*煎り?")
ROAST_LABEL_PATTERN = re.compile(
    r"(?:焙煎度?|roast level)\s*[：:]\s*(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)")
ROAST_EN_PATTERN = re.compile(
    r"(light|medium|full\s*city|city|high|french|italian|cinnamon|right)\s*roast", re.IGNORECASE)
ROAST_EN_MAP = {
    "light": "ライトロースト", "right": "ライトロースト",  # "Right roast"はLightの誤記と判断
    "cinnamon": "シナモンロースト", "medium": "ミディアムロースト",
    "high": "ハイロースト", "city": "シティロースト", "fullcity": "フルシティロースト",
    "french": "フレンチロースト", "italian": "イタリアンロースト",
}
ROAST_KATAKANA_MAP = {
    "ライト": "ライトロースト", "シナモン": "シナモンロースト", "ミディアム": "ミディアムロースト",
    "ハイ": "ハイロースト", "フルシティ": "フルシティロースト", "シティ": "シティロースト",
    "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}

LABEL_NAMES = [
    "生豆生産国", "生産国", "原産国", "地区・地域", "生産地域", "生産地", "地域", "農園名", "農園",
    "標高", "品種", "精製方法", "精製", "焙煎度", "焙煎", "volume", "roast level", "process",
    "altitude", "variety", "flavor",
]
LABEL_PATTERN = re.compile("(" + "|".join(sorted(map(re.escape, LABEL_NAMES), key=len, reverse=True)) + r")\s*[：:]")


def detect_roast(*texts: str | None) -> str | None:
    """焙煎度を表記から検出する(ラベル表記 → 日本語の浅/中/深煎り → 英語表記の順)。"""
    for text in texts:
        if not text:
            continue
        m = ROAST_LABEL_PATTERN.search(text)
        if m:
            return ROAST_KATAKANA_MAP[m.group(1)]
        m = ROAST_JP_PATTERN.search(text)
        if m:
            return m.group(1) + "煎り"
        m = ROAST_EN_PATTERN.search(text)
        if m:
            return ROAST_EN_MAP[re.sub(r"\s+", "", m.group(1).lower())]
        for kw, roast in ROAST_KATAKANA_MAP.items():
            if kw + "ロースト" in text:
                return roast
    return None


def parse_labels(text: str) -> dict:
    """「ラベル：値」が区切りなしで連結された説明文を、ラベルごとの値に分解する。"""
    positions = [(m.start(), m.end(), m.group(1)) for m in LABEL_PATTERN.finditer(text)]
    labels = {}
    for i, (start, end, key) in enumerate(positions):
        value_end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        value = text[end:value_end].strip()
        if value and key not in labels:
            labels[key] = value
    return labels


FARM_NOTE_KEY_JP = {"altitude": "標高", "variety": "品種"}


def build_farm_note(labels: dict) -> str | None:
    parts = []
    for key in ("地区・地域", "生産地域", "生産地", "地域", "農園名", "農園", "標高", "altitude", "品種", "variety"):
        value = labels.get(key)
        if value:
            value = re.split(r"\s+・", value)[0].strip()
            if value:
                parts.append(f"{FARM_NOTE_KEY_JP.get(key, key)}：{value[:60]}")
    return "、".join(parts) or None


def safe_processing(text: str | None) -> str | None:
    """精製方法の自由記述から正規化名を検出する。セミウォッシュ・ドライウォッシュ等の
    複合表記は単純なウォッシュドと誤判定しやすいため、検出対象から外す。"""
    if not text or re.search(r"セミ|semi|dry|ドライ", text, re.IGNORECASE):
        return None
    return detect_processing_method(text)


EXCLUDE_KEYWORDS = [
    "ドリップバッグ", "セット", "フリーズドライ", "リキッド", "カフェオレ", "ギフト",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.IGNORECASE)
TITLE_WEIGHT_SUFFIX = re.compile(r"\s*[｜|]\s*\d+\s*(?:kg|g)\s*$", re.IGNORECASE)
# coffee_parser.pyの国名辞書で検出できない表記の産地(商品説明の記述に基づく)
ORIGIN_OVERRIDES = {
    "hawaii-kona-coffee-100g": "アメリカ(ハワイ)",
}


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    value = int(m.group(1))
    return value * 1000 if m.group(2).lower() == "kg" else value


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("products", [])


def body_text(p: dict) -> str:
    return BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)


def scrape_all_products() -> list[dict]:
    candidates = {}
    for p in fetch_products():
        if p.get("product_type") != "COFFEE":
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue
        weight = parse_weight_g(title)
        if weight is None:
            continue
        name = TITLE_WEIGHT_SUFFIX.sub("", title).strip()
        if name not in candidates or weight < candidates[name][0]:
            candidates[name] = (weight, name, p)

    records = []
    for weight, name, p in candidates.values():
        variants = p["variants"]
        variant = next((v for v in variants if "豆のまま" in (v.get("title") or "")), variants[0])
        available = bool(variant.get("available"))

        text = body_text(p)
        desc = re.sub(r"\s+", " ", text)[:400] or None

        parsed = parse_product(name)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "product_description"

        labels = parse_labels(re.sub(r"\s*\n\s*", " ", text))
        processing = parsed["processing_method"]
        process_text = labels.get("精製") or labels.get("精製方法")
        if not processing and process_text:
            processing = safe_processing(process_text)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"] or detect_roast(text),
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": build_farm_note(labels),
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hugcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hugcoffee.json に出力しました")


if __name__ == "__main__":
    main()
