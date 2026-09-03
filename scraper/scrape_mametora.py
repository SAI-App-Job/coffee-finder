# -*- coding: utf-8 -*-
"""
scrape_mametora.py

豆虎(注文焙煎豆虎、mametora.jp、東京都千代田区神保町、注文毎に生豆から
焙煎する注文焙煎専門店)の商品情報を取得する。WordPressの独自EC(Welcart等の
usces/ss_接頭辞classとは異なる、店舗オリジナルのテーマ)。

robots.txt確認済み(2026-09時点): /mametora/wp-admin/のみDisallow
(admin-ajax.phpは例外的にAllow)。それ以外は制限なし。

【カテゴリ構造による非コーヒー豆の除外】
実データ確認済み: /shop/category/item/配下に「coffee」(コーヒー豆)・
「dripbag」・「gift」・「goods」の4カテゴリがあり、「coffee」タクソノミーが
既にコーヒー豆単品のみに絞られている(フォレスト自家焙煎コーヒー豆店の
"allcoffee"と同じ設計思想)。そのためこのスクレイパーはcoffeeカテゴリの
一覧ページのみを対象とし、キーワードベースの除外は不要。

【一覧ページのみで完結する点について】
実データ確認済み: 一覧ページの各商品カード(`<article>`)に商品名
(h2.item-name)・産地表記(span.orijin-name、無い場合もある)・価格
(div.itemprice、100gあたりの単価)・品切れ表示(div.itemsoldout)が
すべて揃っており、詳細ページを個別に取得しなくても一覧ページだけで
商品データを構築できる(WOODBERRY COFFEEと同じ、一覧完結パターン)。
ページネーションの手がかりが見当たらず、確認できた27件のarticleが
全件と判断した。

【価格について】
実データ確認済み: 「注文焙煎」という業態のため、価格は生豆重量ベースの
100gあたり単価として表示されている(例:「¥14,040/100g」)。
weight_gは100固定とする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "豆虎",
    "url": "https://www.mametora.jp/shop/",
    "platform": "WordPress(独自テーマ)",
    "address": "東京都千代田区神田神保町",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/mametora/wp-admin/のみDisallow、"
                          "それ以外は制限なし)",
}

CATEGORY_URL = "https://www.mametora.jp/shop/category/item/coffee/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRICE_PATTERN = re.compile(r"([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def build_record(article, product_url: str) -> dict | None:
    title_el = article.select_one("h2.item-name")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    parsed = parse_product(title)

    price_el = article.select_one("div.itemprice span")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    if not parsed["origin_country"]:
        origin_el = article.select_one("span.orijin-name")
        if origin_el:
            country = detect_country_name(origin_el.get_text(strip=True))
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "structural"

    structural_out_of_stock = article.select_one("div.itemsoldout") is not None
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    soup = fetch_page(CATEGORY_URL)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for article in soup.select("article"):
        title_el = article.select_one("h2.item-name")
        if not title_el:
            continue
        link_el = article.select_one("div.detail-btn a[href]")
        product_url = link_el.get("href", "") if link_el else ""
        if not product_url:
            continue

        prev = previous.get(product_url)
        title = title_el.get_text(strip=True)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(article, product_url)
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
    with open("data_mametora.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mametora.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
