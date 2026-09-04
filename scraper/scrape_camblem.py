# -*- coding: utf-8 -*-
"""
scrape_camblem.py

CAMBLEM グリーン珈琲焙煎所(camblem.co.jp、千葉県に市川店・モリシア
津田沼店の2店舗、注文毎に焙煎)の商品情報を取得する。Shopify
(/products.json全件取得方式)。2店舗はこのプロジェクトの「11店舗以上の
チェーンは対象外」という基準には該当せず対象内。オンラインショップは
両店舗共通のブランドカタログとして統一されている(店舗別絞り込みは無い)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全60商品中、product_type="コーヒー豆"の44件が対象。
「ギフトセット」(7件)・「ドリップバッグ」(8件)・空文字列(1件)は対象外。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "CAMBLEM グリーン珈琲焙煎所",
    "url": "https://camblem.co.jp/",
    "platform": "Shopify",
    "address": "千葉県市川市市川南1丁目(市川店)",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://camblem.co.jp/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def weight_key(v):
        if v.get("grams"):
            return v["grams"]
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    return min(pool, key=weight_key)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://camblem.co.jp/products/{product.get('handle')}"

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
        if variant.get("grams"):
            weight_g = variant["grams"]
        else:
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
        product_url = f"https://camblem.co.jp/products/{product.get('handle')}"
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
        with open("data_camblem.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_camblem.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
