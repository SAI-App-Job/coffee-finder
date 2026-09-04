# -*- coding: utf-8 -*-
"""
scrape_slowcoffee.py

SLOW COFFEE(slowslowslow.com、千葉県、自家焙煎豆のオンライン販売)の
商品情報を取得する。Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(制限なし)。

【product_typeによるフィルタについて】
実データ確認済み: 全66商品中、product_type="コーヒー"の64件が対象。

【豆のまま/挽き方バリエーションについて】
実データ確認済み: 他のShopify店舗と異なり、option1に挽き方
(粉に挽く(中細挽き)等)、option2に重量(150g等)が入る順序で、標準的な
順序と逆転している。またgramsフィールドは店舗によって信頼できないため、
variant.titleの全文からWEIGHT_PATTERNで重量を抽出する方式
(scrape_eureka.pyと同じ)を用いる。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "SLOW COFFEE",
    "url": "https://slowslowslow.com/",
    "platform": "Shopify",
    "address": "千葉県",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://slowslowslow.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー"
NON_BEAN_KEYWORDS = ["ドリップバッグ", "カフェオレベース", "セット", "飲み比べ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if "豆のまま" in (v.get("title") or "")]
    pool = whole_bean or variants
    available = [v for v in pool if v.get("available")]
    final_pool = available or pool

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    return min(final_pool, key=weight_key)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://slowslowslow.com/products/{product.get('handle')}"

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
        m = WEIGHT_PATTERN.search(variant.get("title") or "")
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
        product_url = f"https://slowslowslow.com/products/{product.get('handle')}"
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
        with open("data_slowcoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_slowcoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
