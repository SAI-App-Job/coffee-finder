# -*- coding: utf-8 -*-
"""
scrape_inokuchicoffee.py

井ノ口珈琲(inokuchi-coffee.jp、岐阜県岐阜市六条片田1丁目15-1、
運営: 株式会社セレス〒500-8359岐阜県岐阜市六条北4-19-12、自家焙煎豆の
オンライン販売)の商品情報を取得する。WordPress+WooCommerce。公開Store
API(/wp-json/wc/store/v1/products)から認証不要で取得する(dots Coffee
Roasters/ひつじ珈琲と同じ方式)。

同一ドメインで姉妹ブランドの焼き菓子店「うずらベーカリー」も運営されて
いるが、店舗数(六条本店・ASTY岐阜店・岐阜城楽市店の3店舗+うずらベー
カリー1店舗の計4店舗)は11店舗未満のため対象。ただしうずらベーカリーの
商品自体(焼き菓子・クッキー缶等)はコーヒー豆ではないためNON_BEAN_KEYWORDS
で除外する。

robots.txt確認済み(2026-09時点): User-agent: *にDisallow指定なし
(YoastのSitemap案内のみ)。Store APIも制限対象外。

【非コーヒー豆商品の除外について】
実データ確認済み: Store APIで返る全28件中、うずらベーカリーの焼き菓子
(クッキー缶・焼き菓子BOX・コーヒータイムセット等、コーヒーとの詰め
合わせも含む)・トートバッグ(グッズ)・カフェ・オレベース(液体)・
ドリップパック各種(単品/ギフトセット)・リキッドアイスコーヒー/珈琲
ゼリー(液体・ゼリー)・ヴィンテージバレル・ギフトセット(ウイスキー樽/
ワイン樽熟成の2種詰め合わせ、単一銘柄と特定できない)が非対象。
NON_BEAN_KEYWORDSで除外する。なお「ヴィンテージバレル・ワイン100g」
「ヴィンテージバレル・ウイスキー100g」はそれぞれ単体では樽熟成珈琲豆
という単一銘柄の商品のため対象に含める。残り8件(ブレンド5種+ストレート
1種+ヴィンテージバレル2種)を対象とする。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "井ノ口珈琲",
    "url": "https://inokuchi-coffee.jp/",
    "platform": "WooCommerce",
    "address": "岐阜県岐阜市六条片田1丁目15-1",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *にDisallow指定なし。"
                          "YoastのSitemap案内のみ。Store APIも制限対象外)",
}

API_URL = "https://inokuchi-coffee.jp/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "羊羹", "ギフトセット", "コーヒータイムセット", "焼き菓子", "クッキー缶",
    "トートバック", "トートバッグ", "カフェ・オレベース", "ドリップパック",
    "リキッドアイス", "珈琲ゼリー",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def build_record(product: dict) -> dict | None:
    name = (product.get("name") or "").strip()
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(name)
    price = product.get("prices", {}).get("price")
    price = int(price) if price is not None else None
    product_url = product.get("permalink")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = not product.get("is_in_stock", True)
    stock_status = detect_stock_status(name, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(name)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
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
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_inokuchicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_inokuchicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
