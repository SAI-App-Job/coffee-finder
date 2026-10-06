# -*- coding: utf-8 -*-
"""
scrape_higashiizucoffee.py

東伊豆珈琲焙煎所(store.higashiizucoffee.jp、静岡県賀茂郡東伊豆町白田185-3)の商品情報を
取得する。Shopify。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点、products.json全28商品): 器具(Coffee Utensils)・
スターターセット・ギフトセット(Welcome to the world of coffee!)を除く、コーヒー豆
14商品(product_typeは「夢中になる一杯」等の味わい別カテゴリ)。

【重量について】
実データ確認済み: 商品説明の1行目に「<国名> <銘柄>(100g)」と袋の容量が明記されている
(variantのgramsは配送重量で0または50のため使わない)。1行目に重量表記が無い
「Vovó CANDINHA」は説明文にも容量の記載が無いためweight_gはnull。
価格はvariant(1つのみ)の価格。「Coming Soon」タグの商品もavailable=trueで購入可能
(ページ上の「Sold out」文言は全商品に存在する非表示ラベルのため使わず、products.jsonの
availableを在庫として採用)。

【焙煎度について】
実データ確認済み: 説明文の1〜2行目に「[ City roast ]」「Medium Roast」等と記載。
(「Right roast」はLight roastの誤記と判断しライトローストとして扱う)
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
    "name": "東伊豆珈琲焙煎所",
    "url": "https://store.higashiizucoffee.jp/",
    "platform": "Shopify",
    "address": "静岡県賀茂郡東伊豆町白田185-3",
    "prefecture": "静岡県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://store.higashiizucoffee.jp"
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


NON_BEAN_TYPES = {"Coffee Utensils", "Welcome to the world of coffee!"}
EXCLUDE_KEYWORDS = ["セット", "ギフト"]
WEIGHT_LINE_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[）)]")
# coffee_parser.pyの国名辞書で検出できない産地(商品名・説明文の記述に基づく)
ORIGIN_OVERRIDES = {
    "東ティモール": "東ティモール",   # 「TIMOR LESTE Renumata (JAS)」(handleは「東ティモール」)
    "vovo-candinha": "ブラジル",      # 説明文「ブラジル・グアリロバ農園」
}


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("products", [])


def body_text(p: dict) -> str:
    return BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        if p.get("product_type") in NON_BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue
        variant = p["variants"][0]

        lines = body_text(p).split("\n")
        first_line = re.sub(r"\s+", " ", lines[0].replace("\xa0", " ").replace("　", " ")).strip()
        weight_m = WEIGHT_LINE_PATTERN.search(first_line)
        weight = int(weight_m.group(1)) if weight_m else None
        # 1行目「<国名> <銘柄>(100g)」から容量表記を除いた部分を商品名とする
        name = re.sub(r"\s+", " ", WEIGHT_LINE_PATTERN.sub("", first_line)).strip() if weight_m else title
        if "decaf" in title.lower() and "decaf" not in name.lower():
            name = f"{name} DeCaf"

        head_text = " ".join(lines[:3])
        desc = re.sub(r"\s+", " ", " ".join(lines[1:]))[:400] or None

        parsed = parse_product(name)
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            for key, country in ORIGIN_OVERRIDES.items():
                if key in p["handle"]:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name" if key != "vovo-candinha" else "product_description"
                    break
        parsed = apply_category_hint_fallback(parsed, title)

        labels = parse_labels(re.sub(r"\s*\n\s*", " ", "\n".join(lines)))
        processing = parsed["processing_method"]
        process_text = labels.get("精製") or labels.get("精製方法")
        if not processing and process_text:
            processing = safe_processing(process_text) or re.split(r"[、／/（(]|\s+・", process_text)[0][:30]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": detect_roast(head_text),
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": build_farm_note(labels),
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if variant.get("available") else "完売",
            "out_of_stock": not variant.get("available"),
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_higashiizucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_higashiizucoffee.json に出力しました")


if __name__ == "__main__":
    main()
