# -*- coding: utf-8 -*-
"""
scrape_mameyafukuoka.py

焙煎工房まめや福岡総本店(coffee-mameya-f.com/online/、〒820-0502
福岡県嘉麻市上臼井328-1、自家焙煎豆専門店)の商品情報を取得する。
WordPress + Welcart(usces、日本製ECプラグイン)。

robots.txt確認済み(2026-09時点): 標準的なWordPressのrobots.txtで
/wp-admin/のみDisallow。本スクレイパーが使うカテゴリページ
(/straight/, /blend/)は制限対象外。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「ストレート」(/straight/、12件)と
「ブレンド」(/blend/、5件)の2カテゴリを合算すると重複を除いて17件
(一部銘柄は両カテゴリに重複掲載)。「ドリップパッグコーヒー『まめや
ブレンド』7枚セット」のみドリップバッグの詰め合わせで単一銘柄の
コーヒー豆ではないため対象外。

【商品情報の取得方法について】
実データ確認済み: カテゴリ一覧ページ自体に`div.beans`ブロックとして
商品名(`p.beans-title`)・価格(`div.beans-price`、税込)が静的HTMLで
直接出力されているため、詳細ページへの個別アクセスは行わない。

【重量について】
実データ確認済み: 大半の商品名に「200g」等の重量が含まれるが、
「キューバ　クリスタルマウンテン」「ペルー カフェオルキデア」
「ハワイ コナ ファンシー」の3件は重量表記が無く、weight_gはnullとする。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "焙煎工房まめや福岡総本店",
    "url": "https://coffee-mameya-f.com/online/",
    "platform": "WordPress + Welcart",
    "address": "福岡県嘉麻市上臼井328-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なWordPressのrobots.txtで"
                          "/wp-admin/のみDisallow、本スクレイパーが使うカテゴリ"
                          "ページは制限対象外)",
}

CATEGORY_URLS = [
    "https://coffee-mameya-f.com/online/straight/",
    "https://coffee-mameya-f.com/online/blend/",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップパッグ", "ドリップパック", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ITEM_PATTERN = re.compile(
    r'<div class="beans"><a href="([^"]+)">.*?<p class="beans-title">([^<]+)</p>.*?'
    r'<div class="beans-price">&yen;([\d,]+)',
    re.DOTALL,
)


def fetch_category_items(url: str) -> list[dict]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    items = []
    for m in ITEM_PATTERN.finditer(resp.text):
        product_url, title, price_text = m.groups()
        title = title.strip()
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        items.append({
            "raw_name": title,
            "product_url": product_url,
            "price": int(price_text.replace(",", "")),
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: dict[str, dict] = {}
    for url in CATEGORY_URLS:
        for item in fetch_category_items(url):
            all_items[item["product_url"]] = item

    records = []
    flavored_records = []
    for item in all_items.values():
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mameyafukuoka.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameyafukuoka.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
