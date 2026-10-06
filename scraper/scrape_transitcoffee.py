# -*- coding: utf-8 -*-
"""
scrape_transitcoffee.py

TRANSIT COFFEE ROASTERS(https://transitlife.thebase.in/、静岡県浜松市中央区卸本町28)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点、sitemap.xml全10商品): コーヒー豆6銘柄(150g)。「初めての方へ【100g×3種類SET】」・「豆選びに迷ったら」(価格77,777円の特殊商品)・ドリップバッグ・ステッカーは除外。
商品名・重量は商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー・SEOキーワード付きのため)。
価格(product:price:amount)・在庫(item_purchasability)・説明(og:description)・
焙煎度・産地・精製・農園情報は商品ページから取得する。

【住所について】
特定商取引法ページの所在地(卸本町28、旧表記は浜松市南区)とAboutページの「卸本町本店 静岡県浜松市中央区卸本町28」で確認(2024年の区再編後の表記は中央区)。焙煎所はCARAVAN店(浜松市中央区住吉5-16-3)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    detect_processing_method,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "TRANSIT COFFEE ROASTERS",
    "url": "https://transitlife.thebase.in/",
    "platform": "BASE",
    "address": "静岡県浜松市中央区卸本町28",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://transitlife.thebase.in"
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


# 精製方法は説明文の「コスタリカハニー」「精製方法 ナチュラル」の記述に基づく。
# 対象商品(商品ID, 商品名, 重量(g)。不明ならNone)。
# category: ブレンド/ストレートの明示(Noneなら商品名から自動判定)
# roast: 焙煎度の明示(Noneなら商品ページから検出、""なら不明として扱う)
# origin: 商品名・説明文から検出できない産地の明示(出典は商品ページの記述)
ITEMS = [
    {'id': '71022999', 'name': 'Costarica コスタリカ 中浅煎', 'weight': 150, 'processing': 'ハニー'},
    {'id': '43591936', 'name': 'Ethiopia エチオピア 浅煎', 'weight': 150, 'processing': 'ナチュラル'},
    {'id': '43592737', 'name': 'Guatemala グァテマラ 中深煎', 'weight': 150},
    {'id': '43590959', 'name': 'Peru ペルー 中煎', 'weight': 150},
    {'id': '43589987', 'name': 'Brazil ブラジル 深煎', 'weight': 150},
    {'id': '43593569', 'name': '【Decafe】Mexico デカフェ/メキシコ', 'weight': 150, 'roast': ''},
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item: dict) -> dict | None:
    item_id, name = item["id"], item["name"]
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
    title_m = TITLE_PATTERN.search(html_text)
    full_title = title_m.group(1) if title_m else ""
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    labels = parse_labels(desc)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item.get("category"):
        parsed["category"] = item["category"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            origin_text = labels.get("生豆生産国") or labels.get("生産国") or labels.get("原産国") or ""
            detected = detect_country_name(origin_text)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, name)
        if item.get("origin"):
            parsed["origin_country"] = item["origin"]
            parsed["origin_source"] = "product_description"

    if item.get("roast") is not None:
        roast_level = item["roast"] or None
    else:
        roast_level = parsed["roast_level"] or detect_roast(full_title, desc)

    processing = parsed["processing_method"]
    if not processing:
        process_text = labels.get("精製方法") or labels.get("精製") or labels.get("process")
        if process_text:
            processing = safe_processing(process_text) or None
    if item.get("processing"):
        processing = item["processing"]

    flavor_notes = labels.get("flavor") or desc[:400] or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": build_farm_note(labels),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": item["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_transitcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_transitcoffee.json に出力しました")


if __name__ == "__main__":
    main()
