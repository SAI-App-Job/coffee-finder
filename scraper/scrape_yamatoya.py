# -*- coding: utf-8 -*-
"""
scrape_yamatoya.py

大和屋珈琲 高崎本店(shop.yamato-ya.jp、群馬県高崎市筑縄町382番地2
〈法人登記住所、株式会社大和屋〉、店舗は同市筑縄町66-22、「木炭焙煎」に
よる自家焙煎豆のオンライン販売)の商品情報を取得する。WordPress+Welcart。
本プロジェクトで初めてのWelcart JSON-LD形式店舗(TABEI COFFEEのWelcart
とは異なり、価格・商品名がPWA用のschema.org Product構造化データとして
埋め込まれている)。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/のみ
Disallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う公開商品
ページは制限対象外。

【商品情報の取得方法について】
実データ確認済み: 各商品ページに`<script type="application/ld+json">`で
schema.org Product構造化データ(name・productID・offers.price)が埋め込ま
れている。価格は税込・円単位の整数。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlは全ページ(固定ページ含む)を列挙する
All in One SEO製で商品ページの絞り込みができないため、コーヒー豆の
4カテゴリページ(coffee-beans/blend-coffee-beans・straight-coffee-beans・
limited-coffee-beans・set-coffee-beans)をそれぞれ取得し、含まれる
商品リンク(数字のみのパス)を和集合で収集する(まめぽっとと同じ方式)。

【非コーヒー豆商品の除外について】
実データ確認済み: set-coffee-beansカテゴリの「おすすめコーヒー豆
ブレンドセット」「おすすめコーヒー豆ストレートセット」の2件が、既存の
単品銘柄を詰め合わせたセット商品のため非対象。NON_BEAN_KEYWORDSで
除外する。残り28件(全て200g)を対象とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "大和屋珈琲 高崎本店",
    "url": "https://shop.yamato-ya.jp/",
    "platform": "Welcart",
    "address": "群馬県高崎市筑縄町382番地2",
    "prefecture": "群馬県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/のみDisallow、"
                          "本スクレイパーが使う公開商品ページは制限対象外)",
}

BASE_URL = "https://shop.yamato-ya.jp"
CATEGORY_PATHS = [
    "coffee-beans/blend-coffee-beans",
    "coffee-beans/straight-coffee-beans",
    "coffee-beans/limited-coffee-beans",
    "coffee-beans/set-coffee-beans",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]
LD_JSON_PATTERN = re.compile(r'<script type="application/ld\+json">(\{.*?\})</script>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    product_ids: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/category/item/{path}/")
        for a in soup.select(f'a[href^="{BASE_URL}/"]'):
            href = a.get("href", "")
            m = re.match(rf"^{re.escape(BASE_URL)}/(\d+)/$", href)
            if m:
                product_ids.add(m.group(1))
    return [f"{BASE_URL}/{pid}/" for pid in product_ids]


def extract_product_ld_json(html: str) -> dict | None:
    for m in LD_JSON_PATTERN.finditer(html):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


def build_record(html: str, product_url: str) -> dict | None:
    data = extract_product_ld_json(html)
    if not data:
        return None
    title = re.sub(r"\s+", " ", (data.get("name") or "")).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    offers = data.get("offers") or {}
    price = offers.get("price")
    price = int(price) if price is not None else None

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

    structural_out_of_stock = offers.get("availability") != "https://schema.org/InStock"
    stock_status = detect_stock_status(title, structural_out_of_stock)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        data = extract_product_ld_json(html)
        title = re.sub(r"\s+", " ", (data.get("name") or "")).strip() if data else ""
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(html, product_url)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_yamatoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamatoya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
