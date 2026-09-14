# -*- coding: utf-8 -*-
"""
scrape_ambercoffee.py

AMBER COFFEE(www.ambercoffee.net、青森県八戸市小中野5丁目2-40、自家焙煎豆
のオンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

【ドメインについて】
候補リストのURL(ambercoffee.jp)はDNS解決不可(存在しない)。実際の公式
オンラインショップは www.ambercoffee.net (Shopify)。

【住所について】
Shopifyの法的表記ページ(https://www.ambercoffee.net/policies/legal-notice)
で実データ確認済み(2026-09時点): 「小中野5丁目2-40」との記載を確認。
候補リストの住所と一致。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【重量について】
実データ確認済み: variants配列のgramsフィールドは実際の重量表記と一致
しない場合がある(例:「ルワンダ ウォッシュト　¥1000/100g」のgramsは120、
「はじめてセット ¥2800/300g」のgramsは400で商品名の300gと不一致)ため
信頼できない。代わりに商品タイトル中の「¥価格/重量g」表記から重量を
直接抽出する。

【挽き方バリエーションについて】
実データ確認済み: 各銘柄は「豆のまま/ペーパーフィルター用/エスプレッソ用」
の挽き方バリアントを持つが価格は同一のため、最初のバリアントの価格を
採用する。

【非コーヒー豆商品の除外について】
実データ確認済み(全15件): ドリップバッグギフト・水出しコーヒーバッグ・
保存用チャック付き袋(梱包資材)・ドリップバッグ単品(インドネシア/
グアテマラ)が非対象。「深煎りセット」「浅煎　酸味系フルーティーセット」
「はじめてセット」は挽き方バリアント名から判断するに複数銘柄を詰め合わせた
福袋的セットと見られ、単一銘柄の特定ができないためNON_BEAN_KEYWORDSで
除外する。残る7件(ルワンダ・タンザニア・ケニア・エチオピア・インドネシア・
グアテマラ・ブラジル)が対象。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "AMBER COFFEE",
    "url": "https://www.ambercoffee.net/",
    "platform": "Shopify",
    "address": "青森県八戸市小中野5丁目2-40",
    "prefecture": "青森県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://www.ambercoffee.net/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト", "水出し", "セット", "保存用", "ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"/\s*(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://www.ambercoffee.net/products/{product.get('handle')}"

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
    price = None
    if variants:
        first_price = variants[0].get("price")
        price = int(float(first_price)) if first_price is not None else None

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        product_url = f"https://www.ambercoffee.net/products/{product.get('handle')}"
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

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_ambercoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ambercoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
