# -*- coding: utf-8 -*-
"""
scrape_kariomon.py

かりおもん(kariomon.com、静岡県藤枝市音羽町、自家焙煎豆のオンライン
販売)の商品情報を取得する。EC-CUBE(Set-Cookie: eccubeで実データ確認済み、
2026-09時点)。

robots.txt確認済み(2026-09時点): https://www.kariomon.com/robots.txtは
404(XSERVERの標準404ページが返り、robots.txt自体が設置されていない)。
User-agent制限が一切存在しないため実質全面許可として扱う。

【カテゴリ構成について】
実データ確認済み: 「コーヒー豆」(category_id=2)・「ドリップバッグ」
(category_id=9)・「器具」(category_id=1)・「セット」(category_id=10)の
4カテゴリのみで、コーヒー豆(category_id=2)は6商品(かりおもんブレンド・
モカ・ブラジル・コロンビア・グアテマラ・マンデリン)のみの小規模店舗。
全商品が200g固定サイズで販売されており(挽き方は選択式だが価格は同一)、
重量違いによる重複は存在しない。カテゴリ一覧ページ1ページに全6商品が
収まっており(ページネーションなし、実データ確認済み)、商品名・価格が
一覧ページ上に直接表示されるため詳細ページへの遷移は不要。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "かりおもん",
    "url": "https://www.kariomon.com/",
    "platform": "EC-CUBE",
    "address": "静岡県藤枝市音羽町3-17-3",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が設置されておらず"
                          "404が返るため、User-agent制限は一切存在しない)",
}

BEAN_CATEGORY_URL = "https://www.kariomon.com/ec/products/list?category_id=2"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRICE_PATTERN = re.compile(r"[\d,]+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def build_record(title: str, price: int | None, product_url: str) -> dict:
    parsed = parse_product(title)

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

    stock_status = detect_stock_status(title)
    weight_m = re.search(r"(\d+)\s*[gｇ]", title)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    soup = fetch_page(BEAN_CATEGORY_URL)

    records = []
    flavored_records = []
    for item in soup.select("div.product_item"):
        link_el = item.select_one("a[href*='/products/detail/']")
        name_el = item.select_one(".item_name")
        price_el = item.select_one(".item_price")
        if not link_el or not name_el:
            continue

        title = name_el.get_text(strip=True)
        product_url = link_el.get("href", "")

        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(0).replace(",", ""))

        detail = build_record(title, price, product_url)
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
    with open("data_kariomon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kariomon.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
