# -*- coding: utf-8 -*-
"""
scrape_saicoffeeroastery.py

Sai Coffee Roastery(下松店、shop.saicoffeeroastery.com、山口県下松市中央町
21-3 下松タウンセンター星プラザ1階、運営：合同会社Sai)の商品情報を取得する。
Shopify(/products.json全件取得方式)。既存のscrape_sai.py(Coffee Roast SAI、
東京都港区)とは無関係の別会社・別店舗のため、ファイル名をsaicoffeeroastery
として区別する。

【住所について】
公式ストアの特定商取引法ページ(https://shop.saicoffeeroastery.com/policies/
legal-notice)で実データ確認済み(2026-09時点): 「販売業者 合同会社Sai / 所在地
〒744-0025 山口県下松市中央町21-3 下松タウンセンター星プラザ1階」。候補
リストの住所と一致。

robots.txt確認済み(2026-09時点): Shopify標準の新しい記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記。
本スクレイパーは対象。

【対象商品の判定について】
実データ確認済み(2026-09時点、全27件): product_typeが「焼⾖」(焼豆=焙煎豆)の
商品のみを対象候補とする。このうち「【送料無料】トライアルコーヒー豆セット
（100g×3種）」(複数銘柄セット)、「《サイの日》深煎/中煎/浅煎コーヒー豆」
(特定銘柄ではなく焙煎度のみを指定した毎月13/31日限定の当日おまかせ販売)の
計4件はNON_BEAN_KEYWORDSで除外する。それ以外のproduct_type(「ドリップ
パック」「ギフトセット」「コーヒー飲料」)はコーヒー豆単品ではないため対象外。
残り12件(産地ストレート10種＋ブレンド2種)を対象とする。

【重量について】
実データ確認済み: ほとんどの商品はvariants[0].gramsが0(未設定)で商品名にも
重量表記が無いが、実店舗のInstagram/店頭表記から基準重量が100gであることを
確認したため、重量表記が無い場合はFIXED_WEIGHT_G=100を採用する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Sai Coffee Roastery",
    "url": "https://shop.saicoffeeroastery.com/",
    "platform": "Shopify",
    "address": "山口県下松市中央町21-3 下松タウンセンター星プラザ1階",
    "prefecture": "山口県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述で\"Public product, "
                          "collection, page, blog, policy, cart, and localized "
                          "HTML is crawlable\"と明記)",
}

PRODUCTS_JSON_URL = "https://shop.saicoffeeroastery.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BEAN_PRODUCT_TYPE = "焼⾖"
NON_BEAN_KEYWORDS = ["トライアル", "《サイの日》", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 100


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(product: dict, title: str) -> bool:
    if product.get("product_type") != BEAN_PRODUCT_TYPE:
        return True
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or is_excluded(product, title):
        return None

    parsed = parse_product(title)
    product_url = f"https://shop.saicoffeeroastery.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = variants[0] if variants else None
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

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

    weight_m = WEIGHT_PATTERN.search(title)
    if weight_m:
        weight_g = int(weight_m.group(1))
    elif variant and variant.get("grams"):
        weight_g = variant["grams"]
    else:
        weight_g = FIXED_WEIGHT_G

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
    with open("data_saicoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_saicoffeeroastery.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
