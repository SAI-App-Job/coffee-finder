# -*- coding: utf-8 -*-
"""
scrape_kcoffee.py

K COFFEE(kcoffee.jp、奈良県大和郡山市柳4-46、自家焙煎豆のオンライン販売)の
商品情報を取得する。Shopify(/products.json全件取得方式)。

注記: 一部の集約サイトでは別エリアの「K COFFEE モリ ロースタリー」も
掲載されているが無関係の別店舗の可能性があるため、本スクレイパーは
kcoffee.jpドメイン(大和郡山市の実店舗、店主: 森和也氏、GIESEN焙煎機導入)
のみを対象とする。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeが信頼できないことについて】
実データ確認済み: 全29商品中、product_typeが空欄("")の豆商品が複数存在
する一方(タンザニアシシュトン、ブラジルアラモサ、秀長ブレンド等)、
グッズ(K SOCKS)にも空欄のものがあるため、product_typeによる判定は
使わずNON_BEAN_KEYWORDSによる商品名ベースの除外方式を採用する
(AKITO COFFEEと同じ方式)。

【非コーヒー豆商品の除外について】
実データ確認済み: ちゃっぽんコーヒー(5種アソート、個数課金の詰め合わせ
商品で単一銘柄と特定できない)・ドリップバッグ各種・大人/キッズの
カフェオレのもと(濃縮液、豆ではない)・K SOCKS各種およびK COFFEE
10周年Tシャツ(グッズ)・コーヒー豆サブスクリプション(定期便)・
コーヒーペーパーフィルター(器具)・店主厳選お試しセット(ちゃっぽん
コーヒーを含む複数銘柄の詰め合わせ)が非対象。NON_BEAN_KEYWORDSで
除外する。残り16件(シングルオリジン15種+秀長ブレンド1種)を対象とする。

【豆/粉バリアントと重量について】
実データ確認済み: 各銘柄は「豆」「粉」の挽き方バリアントを持ち(価格は
同額)、house方針に従い「豆」(粉を含まない)を優先して代表として採用する。
variants配列のgramsフィールドは0または実際の重量と異なる固定値(パナマ
レリダゲイシャの60g/100gバリアントが共にgrams=200等)が入っており
信頼できないため、まずバリアントtitle文字列内の重量表記(例:「豆 200g」)
を正規表現で優先的に読み取り、無ければgramsフィールドにフォールバック
する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "K COFFEE",
    "url": "https://kcoffee.jp/",
    "platform": "Shopify",
    "address": "奈良県大和郡山市柳4-46",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://kcoffee.jp/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ちゃっぽん", "ドリップバッグ", "カフェオレ", "SOCKS", "Tシャツ",
    "サブスクリプション", "ペーパーフィルター", "お試しセット",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def is_whole_bean(v):
        title = v.get("title") or v.get("option1") or ""
        return "豆" in title and "粉" not in title

    whole_bean = [v for v in variants if is_whole_bean(v)]
    pool = whole_bean or variants
    available = [v for v in pool if v.get("available")]
    pool = available or pool

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or v.get("option1") or "")
        if m:
            return int(m.group(1))
        return v.get("grams") or float("inf")

    return min(pool, key=weight_key)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://kcoffee.jp/products/{product.get('handle')}"

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
        weight_g = int(m.group(1)) if m else (variant.get("grams") or None)

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
        if (p.get("title") or "").strip() and not any(kw in p["title"] for kw in NON_BEAN_KEYWORDS)
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

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
