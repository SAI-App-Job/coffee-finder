# -*- coding: utf-8 -*-
"""
scrape_coffeeland.py

コーヒーランド Coffee Land(coffee-land.sakura.ne.jp、東京都江戸川区松島)の
商品情報を取得する。CMS/フレームワークを使わない素朴な静的HTML(さくら
インターネットのレンタルサーバー上の手組みページ、電話・FAX・郵送・
専用カートCGIでの注文)。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、
実質制限なし。

【商品一覧の取得方法について】
実データ確認済み: トップページ1枚に「単品」(ストレート、A01〜A30)
「ブレンド」(B01〜B13)の2セクション、計40商品が`<form>`+`<TABLE>`の
繰り返しとして直書きされており、詳細ページは存在しない(購入は
専用カートCGIへのPOSTのみ)。商品名(`<B>...</B>`)・商品コード・
価格が正規表現で一括抽出できる。

【重量について】
実データ確認済み: ページ冒頭に「表示金額は100g単位の値段です」との
注記があり、全商品が100g単位の価格表示で統一されている。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "コーヒーランド",
    "url": "https://coffee-land.sakura.ne.jp/",
    "platform": "独自HTML(さくらインターネット)",
    "address": "東京都江戸川区松島2丁目",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず、実質制限なし)",
}

BASE_URL = "https://coffee-land.sakura.ne.jp/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRODUCT_ROW_PATTERN = re.compile(
    r"<B>([^<]+)</B></TD>\s*<TD width=400>([^<]*)</TD>\s*<TD width=40>([^<]*)</TD>\s*<TD width=50>(\d+)円</TD>"
)


def fetch_html() -> str:
    resp = requests.get(BASE_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    html = fetch_html()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for m in PRODUCT_ROW_PATTERN.finditer(html):
        title, _desc, code, price_text = m.group(1).strip(), m.group(2), m.group(3).strip(), m.group(4)
        product_url = f"{BASE_URL}#{code}"

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        parsed = parse_product(title)
        price = int(price_text)

        if parsed["is_flavored"]:
            flavored_records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": title,
                "category": "フレーバー",
                "is_flavored": True,
                "flavor_name": parsed["flavor_name"],
                "price": price,
                "product_url": product_url,
            })
            continue

        stock_status = detect_stock_status(title)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 100,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": product_url,
        })

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeeland.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeland.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
