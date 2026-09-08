# -*- coding: utf-8 -*-
"""
scrape_minohcoffee.py

大阪箕面珈琲珈琲焙煎所(minoh-coffee.net、大阪府池田市神田1-22-8、自家焙煎豆の
販売)の商品情報を取得する。

【店舗名の「箕面」表記と実際の所在地について】
実データ確認済み: 屋号・ドメインは「箕面」を冠するが、特定商取引法に基づく
表記(https://minoh-coffee.net/company/ )に記載の実住所は大阪府池田市神田
1丁目22番8号。本スクレイパーではこの実住所を採用する。

【プラットフォーム/取得元ページについて】
実データ確認済み: BASEの白ラベルドメイン(minohcoffee.base.shop)を保有して
いるが、そちらの商品ページは「数十種類のコーヒー豆から選べるセット」形式
(og:descriptionに明記: 「数十種類のコーヒー豆から３種類のコーヒー豆を選べる
セットです」)のみで、固定された単一銘柄の商品ページが存在しない。実際の
銘柄別ラインナップ(産地・農園・価格)は自社サイトの単品カテゴリページ
(https://minoh-coffee.net/itemcat/single/ )に一覧掲載されているため、本
スクレイパーはこちらを取得元とする(同ページの価格表記は「/100g」の単価で
あり、購入自体はBASEの選べるセット経由となる旨がog:description内に明記され
ているが、産地・銘柄・単価は自社サイトの一次情報であるため採用する)。

robots.txt確認済み(2026-09時点): minoh-coffee.netはWordPress標準の
robots.txt(/wp/wp-admin/のみDisallow、admin-ajax.phpはAllow)で実質許可。

【非コーヒー豆商品の除外について】
実データ確認済み: /itemcat/single/ページは全16件が単一産地のストレート豆
(一部「アイスライト」「アイスダーク」等の焙煎違い表記を含む)のみで構成
されており、器具・ギフト等の非対象商品は無い。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "大阪箕面珈琲珈琲焙煎所",
    "url": "https://minoh-coffee.net/",
    "platform": "独自(WordPress、単品ラインナップページ。購入はBASE"
                "〈minohcoffee.base.shop〉の選べるセット経由)",
    "address": "大阪府池田市神田1-22-8",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。WordPress標準robots.txt、"
                          "/wp/wp-admin/のみDisallow)",
}

BASE_URL = "https://minoh-coffee.net"
LISTING_URL = f"{BASE_URL}/itemcat/single/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS: list[str] = []
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_items() -> list[dict]:
    soup = fetch_page(LISTING_URL)
    items = []
    for block in soup.select("div.item_info"):
        name_el = block.select_one(".item_name h2")
        if not name_el:
            continue
        title = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        link_el = block.select_one("a[href]")
        product_url = link_el["href"] if link_el else LISTING_URL

        price_el = block.select_one(".price")
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text(" ", strip=True))
            if m:
                price = int(m.group(1).replace(",", ""))

        items.append({"title": title, "price": price, "url": product_url})
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        # 自社サイトの価格表記は100gあたりの単価(購入はBASEの選べるセット経由の
        # ため固定包装重量が存在しない)。
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_items()

    records = []
    flavored_records = []
    for item in items:
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
    with open("data_minohcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_minohcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
