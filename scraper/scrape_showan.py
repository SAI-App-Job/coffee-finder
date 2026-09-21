# -*- coding: utf-8 -*-
"""
scrape_showan.py

焙煎珈琲工房 梢庵(しょうあん、sho-an.jp、島根県松江市玉湯町林223-3、運営：
有限会社ティーワイティー、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式、独自ドメインがそのままShopify上で
運用されている)。

【住所について】
公式ストアの特定商取引法ページ(https://sho-an.jp/pages/specified)で実データ
確認済み(2026-09時点): 「事業者の名称 有限会社ティーワイティー / 事業責任者の
氏名 豊田文男 / 住所 島根県松江市玉湯町林223番地3」。候補リストの住所
(〒699-0204 島根県松江市玉湯町林223-3)と一致(候補リストにあった「玉湯町
玉造1218-8」という別住所は、Web検索で混同されていた誤情報と判断し採用しない)。

robots.txt確認済み(2026-09時点): Shopify標準の記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記。
本スクレイパーは対象。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全23件): ドリップパック各種(スペシャル
ブレンド・マイルドブレンド・梢庵ブレンドのドリップパック版)、梢庵ドリップ
バッグコーヒーゼリー(菓子)、ドリップバッグアイスコーヒー、水出しアイス珈琲、
各種セット商品(梢庵オリジナルブレンドとドリップパックセット・梢庵厳選
コーヒーセット・梢庵オリジナルブレンドセット・梢庵お手軽3点セット・梢庵
ドリップパックセット)がNON_BEAN_KEYWORDSで除外される。残り12件(産地
ストレート8種＋ブレンド4種、いずれも豆売り)を対象とする。

【重量について】
実データ確認済み: variantsのoption1が「100g」のように重量そのものを表す
文字列になっており(grams フィールドは0で未設定)、option2が挽き方(豆のまま/
細挽き等)。option2に「豆のまま」を含むバリアントを代表とし、option1から
正規表現で重量を取得する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlにテイスティング文が直接入っており(対象12件
全て確認)、うち2件は末尾に「生産国／<国名>」というスペック行が続く
ため、その手前までを採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "焙煎珈琲工房 梢庵",
    "url": "https://sho-an.jp/",
    "platform": "Shopify",
    "address": "島根県松江市玉湯町林223-3",
    "prefecture": "島根県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述で\"Public product, "
                          "collection, page, blog, policy, cart, and localized "
                          "HTML is crawlable\"と明記)",
}

PRODUCTS_JSON_URL = "https://sho-an.jp/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップパック", "ドリップバッグ", "ゼリー", "水出し", "セット",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 100
FLAVOR_STOP_PATTERN = re.compile(r"生産国／")


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text(" ", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[: m.start()]
    return text.strip() or None


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if "豆のまま" in (v.get("option2") or "")]
    pool = whole_bean or variants
    return pool[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://sho-an.jp/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

    weight_m = WEIGHT_PATTERN.search(variant.get("option1") or "") if variant else None
    weight_g = int(weight_m.group(1)) if weight_m else FIXED_WEIGHT_G

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

    all_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, all_out_of_stock)

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
        "flavor_notes": extract_flavor_notes(product.get("body_html")),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

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
    with open("data_showan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_showan.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
