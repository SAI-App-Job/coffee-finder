# -*- coding: utf-8 -*-
"""
scrape_damokaffee.py

DAMO Kaffee Haus(damokaffee.thebase.in、宮城県仙台市青葉区本町2-10-5、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(宮城県)で発見(kitsune-coffee.com「仙台のおすすめコーヒー豆
専門店18選」)。

【対象商品について】
実データ確認済み(sitemap.xml全28件、2026-09時点): カフェオレベース・
ドリップバッグ単品/セット・水出しコーヒーパック・各種BOXギフトセットを
除いた、100g/200gの2サイズ展開のコーヒー豆9銘柄(ストレート8・ブレンド1)
を対象とする。各銘柄の100gパック価格を代表として採用。

【商品説明の構造について】
実データ確認済み: og:descriptionはテイスティング文の後に「※」で始まる
配送方法の定型文が続く構成。「※」以降を除去してflavor_notesとして
採用する。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "DAMO Kaffee Haus",
    "url": "https://damo.lomo.jp/index.html",
    "platform": "BASE",
    "address": "宮城県仙台市青葉区本町2-10-5",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(BASE標準構成を想定)",
}

BASE_URL = "https://damokaffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["カフェオレ", "ドリップバッグ", "水出し", "ギフト", "COLD"]
TARGET_100G_IDS = [
    "103220065", "103220461", "153121866", "23582813", "23563548",
    "23587596", "23588074", "23739791", "23740457",
]


def build_record(pid: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{pid}", headers=REQUEST_HEADERS, timeout=20)
    html = resp.text
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if not title_m:
        return None
    title = title_m.group(1).split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', html)
    price = int(float(price_m.group(1))) if price_m else None
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    desc = desc_m.group(1) if desc_m else ""
    flavor_notes = desc.split("※")[0].strip() or None

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{pid}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    detected = detect_country_name(title) or (flavor_notes and detect_country_name(flavor_notes))
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in TARGET_100G_IDS:
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_damokaffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_damokaffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
