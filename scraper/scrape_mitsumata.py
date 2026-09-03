# -*- coding: utf-8 -*-
"""
scrape_mitsumata.py

MITSUMATA COFFEE(shop.mitsumatacoffee.com、東京都品川区大井)の商品情報を
取得する。Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtで`Allow: /`
(標準テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全22商品中、product_type="焙煎豆"の13件のみが
コーヒー豆(ブレンド4種+ストレート9種)。他は「物版品」(ラバーコースター・
キャップ等のグッズ、4件)・「MANUKA HONEY」(マヌカハニー、1件)・
「CHAI」(チャイ、1件)・「ドリップバック」(3件)でコーヒー豆そのもの
ではないため対象外。

【豆/粉バリエーションについて】
実データ確認済み: 各商品のバリエーションは「重量(90g/180g)」×
「形態(Beans（豆）/Powder（粉）)」の組み合わせ。挽いた粉ではなく
豆のまま・最小重量(90g)のバリエーションを代表として採用する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "MITSUMATA COFFEE",
    "url": "https://shop.mitsumatacoffee.com/",
    "platform": "Shopify",
    "address": "東京都品川区大井4-1-2",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://shop.mitsumatacoffee.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "焙煎豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    beans_variants = [v for v in variants if "Beans" in (v.get("option2") or "")]
    pool = beans_variants or variants
    if not pool:
        return None

    def sort_key(v):
        m = WEIGHT_PATTERN.search(v.get("option1") or "")
        return int(m.group(1)) if m else float("inf")

    available = [v for v in pool if v.get("available")]
    final_pool = available or pool
    return min(final_pool, key=sort_key)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://shop.mitsumatacoffee.com/products/{product.get('handle')}"

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
    weight_g = None
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("option1") or "")
        if m:
            weight_g = int(m.group(1))

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
    targets = [p for p in products if p.get("product_type") == TARGET_PRODUCT_TYPE]
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        product_url = f"https://shop.mitsumatacoffee.com/products/{product.get('handle')}"
        title = (product.get("title") or "").strip()
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        products = fetch_products()
        match = next((p for p in products if p.get("handle") == sys.argv[1]), None)
        print(json.dumps(build_record(match) if match else None, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_mitsumata.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mitsumata.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
