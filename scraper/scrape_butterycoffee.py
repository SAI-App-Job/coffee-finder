# -*- coding: utf-8 -*-
"""
scrape_butterycoffee.py

Buttery Coffee 名駅桜通店(buttery-coffee.jp、愛知県名古屋市中村区名駅
2-36-20アイムビル〈名古屋駅地下街ユニモールU14出口すぐ〉、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全14商品中、product_type="コーヒー豆"の5件
(バタリーブレンド・グアテマラSHB・コスタリカセントタラスSHBガンボア
農園・ブルボンアマレロアルコイリス農園・エチオピアモカイルガチェフェ
G1)が対象。product_type="ドリップバッグ"(バタリーブレンド深煎り
(ドリップバッグ))と"オリジナルグッズ"(タンブラー・トートバッグ・
キャニスター・マグ等)は非対象。

【重量バリエーションについて】
実データ確認済み: 他店と異なり各銘柄はvariants.gramsが0固定で、
重量ごとの個別バリアントを持たない。代わりに「豆（100g単位での
販売です）」「粉（100g単位での販売です）」という2バリアント
(挽き方違い、価格は同一)があり、購入時に個数指定で100g単位の
数量を選ぶ方式。「豆」バリアントを優先して代表として採用し(house
ルールの豆優先方針)、重量は変数名の"100g単位"表記から100gを固定値
として抽出する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Buttery Coffee 名駅桜通店",
    "url": "https://buttery-coffee.jp/",
    "platform": "Shopify",
    "address": "愛知県名古屋市中村区名駅2-36-20アイムビル",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://buttery-coffee.jp/products.json?limit=250"
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

    def is_whole_bean(v):
        title = v.get("title") or v.get("option1") or ""
        return "豆" in title and "粉" not in title

    whole_bean = [v for v in pool if is_whole_bean(v)]
    return (whole_bean or pool)[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://buttery-coffee.jp/products/{product.get('handle')}"

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
        variant_title = variant.get("title") or variant.get("option1") or ""
        m = WEIGHT_PATTERN.search(variant_title)
        weight_g = int(m.group(1)) if m else None

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

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_butterycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_butterycoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
