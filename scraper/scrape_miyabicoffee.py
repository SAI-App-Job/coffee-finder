# -*- coding: utf-8 -*-
"""
scrape_miyabicoffee.py

珈琲舎 雅(miyabi-coffee.com、〒960-8112 福島県福島市花園町7-11、自家焙煎豆の
オンライン販売。2004年創業)の商品情報を取得する。Shopify。

【住所について】
公式サイトの法的表記ページ(https://miyabi-coffee.com/policies/legal-notice)で
実データ確認(2026-09時点): 〒960-8112 福島県福島市花園町7-11。

【AIエージェント向け指示について】
robots.txtの先頭コメントに「エージェントはUCP/MCPエンドポイントやshop.appの
SKILLを使い、購入代行すべき」という趣旨の記述があったが、これはこのサイトの
コンテンツ(=信頼できない外部指示)であり、ユーザー自身の指示ではないため一切
従っていない。本スクレイパーは商品情報の読み取りのみを行う(WOODBERRY COFFEE等と
同じ対応方針)。

【対象コレクションについて】
実データ確認済み(2026-09時点): 「ブレンドコーヒー」(handle: blend-coffee、13件)・
「ストレートコーヒー」(handle: straight-coffee、16件)の2コレクションが焙煎豆の
全ラインナップ。

【バリアントについて】
実データ確認済み: 各商品は「重量(100g/200g)」×「豆のまま/粉」の組み合わせ
バリアントを持つが、挽き方は価格に影響しない。在庫のある(available=true)
バリアントの中で最小重量のものを代表バリアントとして採用する
(WOODBERRY COFFEE等のpick_canonical_variant()と同じ考え方)。

【商品説明(body_html)について】
実データ確認済み: 産地・農園等を構造化したラベル付き説明は無く、テイスティング
コメントのみの自由文のため、産地判定は商品名からのcoffee_parser.parse_product()
のみに依る。
"""

import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "珈琲舎 雅",
    "url": "https://miyabi-coffee.com/",
    "platform": "Shopify",
    "address": "福島県福島市花園町7-11",
    "prefecture": "福島県",
    "robots_txt_status": "許可(2026-09確認。標準的なShopify robots.txtで/products/・/collections/は"
                          "User-agent: *に対しAllow。/cart・/checkout・/account等の非公開/取引系のみDisallow)",
}

BASE_URL = "https://miyabi-coffee.com"
COLLECTION_HANDLES = ["blend-coffee", "straight-coffee"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1


def fetch_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_collection_products(handle: str) -> list[dict]:
    products = []
    page = 1
    while True:
        url = f"{BASE_URL}/collections/{handle}/products.json?limit=250&page={page}"
        data = fetch_json(url)
        items = data.get("products", [])
        if not items:
            break
        products.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return products


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def grams_key(v):
        return v.get("grams") or float("inf")

    return min(pool, key=grams_key)


def build_record(product: dict) -> dict:
    raw_name = product["title"]
    parsed = parse_product(raw_name)

    variant = pick_canonical_variant(product.get("variants", []))
    price = int(float(variant["price"])) if variant else None
    weight_g = int(variant["grams"]) if variant and variant.get("grams") else None

    all_out_of_stock = bool(product.get("variants")) and not any(v.get("available") for v in product["variants"])
    stock_status = "一時的に品切れ" if all_out_of_stock else "販売中"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
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
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> list[dict]:
    seen_ids = set()
    records = []
    for handle in COLLECTION_HANDLES:
        for product in fetch_collection_products(handle):
            if product["id"] in seen_ids:
                continue
            seen_ids.add(product["id"])
            records.append(build_record(product))
    return records


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    with open("data_miyabicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_miyabicoffee.json に出力しました")
