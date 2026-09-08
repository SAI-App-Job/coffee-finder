# -*- coding: utf-8 -*-
"""
scrape_taisanji.py

太山寺珈琲焙煎室(shop.taisanji-coffee-works.jp、〒651-2108 兵庫県神戸市西区
伊川谷町前開265-1、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式)。運営会社サイト本体(www.taisanji-
coffee-works.jp)はWixだが、ショップサブドメインはShopifyで独立して構築
されている。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全44商品中、product_type="beans"の18件が焙煎豆
カテゴリ。このうち「スタッフブレンド「つむぐ」飲み比べセット
（100g×4）」「ブレンド飲み比べセット（100g×4）」の2件は複数銘柄の
飲み比べアソートで単一銘柄ではないためNON_BEAN_KEYWORDSで別途除外
する。残り16件(月替わりブレンド・定番ブレンド3種+シングルオリジン
11種、うちカフェインレス2種を含む)を対象とする。ギフト(type='ギフト')・
コーヒージュレ・アイスコーヒー/カフェオレベース・ドリップバッグ&水出し・
グッズ(Tシャツ/STTOKE)・セミナーは product_type フィルタで自動的に
除外される。

【重量バリエーションについて】
実データ確認済み: 対象16件は全て200gの単一バリアントのみ(重量違いの
複数バリアントを持つ商品は無い)。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "太山寺珈琲焙煎室",
    "url": "https://shop.taisanji-coffee-works.jp/",
    "platform": "Shopify",
    "address": "兵庫県神戸市西区伊川谷町前開265-1",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://shop.taisanji-coffee-works.jp/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "beans"
NON_BEAN_KEYWORDS = ["飲み比べセット"]
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
    product_url = f"https://shop.taisanji-coffee-works.jp/products/{product.get('handle')}"

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
    targets = [
        p for p in products
        if p.get("product_type") == TARGET_PRODUCT_TYPE
        and not any(kw in (p.get("title") or "") for kw in NON_BEAN_KEYWORDS)
    ]
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        product_url = f"https://shop.taisanji-coffee-works.jp/products/{product.get('handle')}"
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

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_taisanji.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_taisanji.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
