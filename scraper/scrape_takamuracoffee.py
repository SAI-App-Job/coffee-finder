# -*- coding: utf-8 -*-
"""
scrape_takamuracoffee.py

TAKAMURA COFFEE ROASTERS(takamura-coffee.com、大阪府大阪市西区江戸堀2-2-18
〈タカムラ株式会社〉、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

住所は公式サイトの商品説明欄(【製造・加工・販売業者名及び住所】タカムラ
株式会社 〒550-0002 大阪府大阪市江戸堀2-2-18)および/pages/visit、
/pages/infoページ(大阪市西区江戸堀2丁目2-18)で確認。

【product_typeによるフィルタについて】
実データ確認済み: 全25商品中、product_type="コーヒー豆"の24件が対象候補。
「コーヒーゼリー(COFFEE JELLY FLIGHT)」1件のみproduct_type空欄で、
フィルタにより自動的に除外される。

【非コーヒー豆商品の除外について】
実データ確認済み: product_type="コーヒー豆"の中にも、以下の複数銘柄
アソート商品が3件混入している。いずれも単一銘柄と特定できないため
NON_BEAN_KEYWORDSで除外する。
- 「50g×2種 最高級ゲイシャ お試しセット(パナマ・エスメラルダ・ゲイシャ
  × グァテマラCOE)」
- 「70g×3種入 お試しコーヒーセット(エチオピア・ブラジル・コロンビア)」
- 「250g×2種入 産地を楽しむ飲み比べ アソートコーヒーセット
  (インドネシア・アヴァタラ・ガヨ / ゴールド・トップ・マンデリン)」

【重量バリエーションについて】
実データ確認済み: 大半の銘柄が250g/500g/1000g(一部2000gも)の
バリアントを持つ(ゲイシャ・COE系のみ100g/250g/500g)。variants配列の
gramsから最小重量を代表として採用する。一部商品(タイCOE、グァテマラ
COE等)はgramsが0のまま未設定のため、バリアントtitle文字列内の
重量表記(例: 「100g / 豆のまま」)から正規表現でフォールバック取得する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "TAKAMURA COFFEE ROASTERS",
    "url": "https://takamura-coffee.com/",
    "platform": "Shopify",
    "address": "大阪府大阪市西区江戸堀2-2-18",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://takamura-coffee.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー豆"
NON_BEAN_KEYWORDS = ["お試し", "アソートコーヒーセット"]
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
    product_url = f"https://takamura-coffee.com/products/{product.get('handle')}"

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
        product_url = f"https://takamura-coffee.com/products/{product.get('handle')}"
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
    with open("data_takamuracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_takamuracoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
