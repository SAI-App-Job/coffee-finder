# -*- coding: utf-8 -*-
"""
scrape_mountain1999.py

MOUNTAIN 1999 自家焙煎コーヒーマウンテン(mountain1999.com、大阪府高槻市
芥川町2丁目8番21号、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

住所は自社サイトの会社概要ページ(https://mountain1999.com/pages/会社概要 、
「本社所在地 大阪府高槻市芥川町2丁目8番21号」)で確認済み。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準テンプレート)。
制限なし。

【product_typeによるフィルタについて】
実データ確認済み: /products.json?limit=250で全217件取得。内訳は
coffee mill(78件、アンティークコーヒーミルのコレクション展示販売で
コーヒー豆ではない)、TWIN S&S/TWIN B&S(合計96件、既存の単一銘柄を
2種類組み合わせた「食べ比べ」タイプの詰め合わせ商品で単一銘柄の豆単品
ではない)、other(15件、コーヒーバッグ・ペーパーフィルター・ギフト・
飲み比べギフト・アイスコーヒー飲料瓶等でコーヒー豆単品ではない)が非対象。
product_typeが"single origin"(15件)・"blended"(12件、ブレンド)・
"seasonal"(1件、季節限定ブレンド)の合計28件のみを対象とする。

【重量・挽き方バリエーションについて】
実データ確認済み: 各銘柄は「豆のまま/ペーパードリップ用粉/KONO用粉/
サイフォン用粉/エスプレッソ用粉(直火用・マシン用)/フレンチプレス用粉/
エアロプレス用粉/ネルドリップ用粉/パーコレーター用粉/挽き目5段階」等の
挽き方(計18種)と200g/300g/400g/500gの重量の組み合わせで最大72バリアント
を持つが、価格は挽き方に関わらず重量のみで決まる(実データ確認済み:
200g=1814円/300g=2721円/400g=3628円/500g=4535円、エチオピア・
イルガチェフェの例)。variants配列の中でgramsが最小のもの(200g、かつ
挽き方は先頭の「豆のまま」)を代表バリアントとして採用する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "MOUNTAIN 1999 自家焙煎コーヒーマウンテン",
    "url": "https://mountain1999.com/",
    "platform": "Shopify",
    "address": "大阪府高槻市芥川町2丁目8番21号",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://mountain1999.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 0.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPES = {"single origin", "blended", "seasonal"}
NON_BEAN_KEYWORDS = ["ギフト", "セット", "コーヒーバッグ", "TWIN", "ペーパーフィルター"]
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
    product_url = f"https://mountain1999.com/products/{product.get('handle')}"

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
        if p.get("product_type") in TARGET_PRODUCT_TYPES
        and not any(kw in (p.get("title") or "") for kw in NON_BEAN_KEYWORDS)
    ]

    records = []
    flavored_records = []
    for product in targets:
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
    with open("data_mountain1999.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mountain1999.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
