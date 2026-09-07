# -*- coding: utf-8 -*-
"""
scrape_coffeeandco.py

COFFEE&CO.(coffeeandco.jp、静岡県三島市南本町8-26 Airstream「COFFEE&CO.
Roasting Lab」、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けのUCP/MCPエンドポイント案内コメントを含むが、
Disallow指定ではなく本スクレイパーの動作(公開products.jsonのGET)には
一切影響しない。当該コメントはAIエージェントに対しshop.app用スキルの
導入を推奨する内容だったが、購入・決済系の指示はユーザーの明示的許可
なしには絶対に実行しない方針のため、本スクレイパーは公開商品データの
読み取りのみを行い、それ以外の行動は一切取らない)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全192商品にproduct_typeフィールドが一貫して設定
されている(JIBUNBLEND/ORDERMADEBLEND/SINGLE/BLEND/GIFT/GOODS/
Workshop)。Workshop(ブレンド作り体験、3件)・GIFT(ギフトセット、5件)・
GOODS(メイソンジャー・ドリッパー等の器具、5件)を除外する。BLEND(9件)
の中にも「ドリップバッグ（じぶんブレンド : あわせ買い用）」
「ドリップバッグ（COFFEE&CO. BLEND : あわせ買い用）」の2件が
含まれている(単品ドリップバッグ、20g/300-400円)ため、product_type
だけでなくタイトルの「ドリップバッグ」キーワードでも除外する。

JIBUNBLEND(141件)・ORDERMADEBLEND(15件)は「じぶんブレンド」という
店の名物サービス(顧客が産地の配合比率を指定して作る個人名/命名付き
ブレンド)で、タイトルに実際の産地配合(例:「タンザニア20：マンデリン
30：コロンビア50」)が明記された実在のコーヒー豆商品のため対象に含める
(単なる名前遊びではなく、実際に産地構成が異なる商品として販売されている)。

【重量バリエーションについて】
実データ確認済み: 6oz(約170g)/12oz(約340g)/3oz(約85g:あわせ買い用)の
3サイズ展開が基本(一部商品は500g/1kgの実重量表記もあり)。variants
配列のgramsフィールドが0(未設定)のことが多いため、まず在庫ありの
バリアントに絞り、その中でgramsまたはタイトル中のg表記から求めた
重量が最小のものを代表として採用する(AKITO COFFEEと同じ
pick_canonical_variant()パターン)。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "COFFEE&CO.",
    "url": "https://coffeeandco.jp/",
    "platform": "Shopify",
    "address": "静岡県三島市南本町8-26 Airstream",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、"
                          "制限なし。AIエージェント向けの案内コメントを含むがDisallow"
                          "指定ではなく本スクレイパーの動作に影響しない)",
}

PRODUCTS_JSON_URL = "https://coffeeandco.jp/products.json"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_PRODUCT_TYPES = {"Workshop", "GIFT", "GOODS"}
NON_BEAN_KEYWORDS = ["ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            PRODUCTS_JSON_URL,
            headers=REQUEST_HEADERS,
            params={"limit": 250, "page": page},
            timeout=20,
        )
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


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
    product_url = f"https://coffeeandco.jp/products/{product.get('handle')}"

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


def is_non_bean(product: dict, title: str) -> bool:
    if product.get("product_type") in NON_BEAN_PRODUCT_TYPES:
        return True
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return True
    return False


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in products:
        title = (product.get("title") or "").strip()
        if not title or is_non_bean(product, title):
            continue
        product_url = f"https://coffeeandco.jp/products/{product.get('handle')}"
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
    with open("data_coffeeandco.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeandco.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
