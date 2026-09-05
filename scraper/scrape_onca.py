# -*- coding: utf-8 -*-
"""
scrape_onca.py

ONCA COFFEE & ROASTERY 前橋店(onca-coffee.shop、群馬県前橋市、自家焙煎豆の
オンライン販売。運営: 株式会社ジンズ。前橋・天神・神田・新宿の4店舗展開
だが「11店舗以上のチェーンは対象外」の基準には該当しないため対象内)の
商品情報を取得する。Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み: 全33商品にproduct_typeが設定されていないため、
商品名でのキーワード除外方式を使う。ICE COFFEE BAG(液体)・ドリップ
バッグ各種(単品・ギフト・アソート・コンプリート・テイスティング・
マンスリーセット)・タンブラー/コーヒーサーバー/ドリップスケール/
マグカップ/キャップ(器具・雑貨)が非対象。NON_BEAN_KEYWORDSで除外する。
残り11件(豆)を対象とする。

【重量バリエーションについて】
実データ確認済み: 焙煎豆は100g/200gの2バリアントを持つ(KENYA AAのみ
100g単一)。variants配列のgramsから最小重量(100g)を代表として採用する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ONCA COFFEE & ROASTERY 前橋店",
    "url": "https://onca-coffee.shop/",
    "platform": "Shopify",
    "address": "群馬県前橋市",
    "prefecture": "群馬県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://onca-coffee.shop/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ICE COFFEE BAG", "ドリップバッグ", "セット", "タンブラー",
    "コーヒーサーバー", "ドリップスケール", "マグカップ", "キャップ",
]
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
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://onca-coffee.shop/products/{product.get('handle')}"

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
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in products:
        title = (product.get("title") or "").strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        product_url = f"https://onca-coffee.shop/products/{product.get('handle')}"
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
    with open("data_onca.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_onca.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
