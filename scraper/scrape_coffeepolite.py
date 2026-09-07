# -*- coding: utf-8 -*-
"""
scrape_coffeepolite.py

珈琲豆屋ぽらいと(coffee-polite.com、愛知県春日井市神明町35、自家焙煎豆の
オンライン販売)の商品情報を取得する。WordPress+WooCommerce。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/等の管理系
パスのみDisallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う
Store API(`/wp-json/wc/store/products`)は制限対象外。

【商品構成について】
実データ確認済み: 全7商品中、焙煎豆単品は4件(「【単一農園】陰（いん）
中深煎り」「【単一農園】陽（よう）中浅煎り」「ぽらいとぶれんど　蒼
（あお）深煎り」「ぽらいとぶれんど　青（あお）中煎り」、蒼と青は同じ
「あお」の読みだが別の当て字・別ブレンドの2商品)。残り3件は「【贈り物】
ドリップパック」「ドリップパック」(ギフト用ドリップバッグ)と「水出し
珈琲　深煎り」(50g入り抽出用パックを3袋/5袋単位で購入する形式、
商品ページのバリアント属性(attribute_量)が"3袋"/"5袋"というパック数
指定でありグラム指定の重量バリエーションではないため、ドリップパックと
同種として扱い対象外)。NON_BEAN_KEYWORDSで除外する。

【重量バリエーションの取得について】
実データ確認済み: 焙煎豆単品は「量」(100g/150g/200g/500g)×「豆の状態」
(豆/粉（中挽き）)の変動商品(variable product)。Store APIの商品一覧には
重量が含まれないため、各商品の通常ページHTMLに埋め込まれたWooCommerce
標準の`data-product_variations`属性(HTMLエンティティ化されたJSON)から
各バリアントのattributes(キー名は商品属性のスラッグ化された日本語で
店舗ごとに異なるため、値の内容で判定する)を走査し、値に「g/ｇ」を含む
ものを重量、「豆」の一致(「粉」を含まない)を全粒(豆のまま)と判定して、
在庫があるバリアントの中から最小重量かつ全粒優先で代表を選ぶ。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲豆屋ぽらいと",
    "url": "https://coffee-polite.com/",
    "platform": "WooCommerce",
    "address": "愛知県春日井市神明町35",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等の管理系パスのみ"
                          "Disallow。本スクレイパーが使うStore APIは制限対象外)",
}

API_URL = "https://coffee-polite.com/wp-json/wc/store/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップパック", "水出し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
VARIATIONS_PATTERN = re.compile(r'data-product_variations="([^"]*)"')


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def fetch_variations(permalink: str) -> list[dict]:
    resp = requests.get(permalink, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    m = VARIATIONS_PATTERN.search(resp.text)
    if not m:
        return []
    try:
        return json.loads(html.unescape(m.group(1)))
    except json.JSONDecodeError:
        return []


def variation_weight_g(variation: dict) -> int | None:
    for value in (variation.get("attributes") or {}).values():
        m = WEIGHT_PATTERN.search(value or "")
        if m:
            return int(m.group(1))
    return None


def is_whole_bean_variation(variation: dict) -> bool:
    values = list((variation.get("attributes") or {}).values())
    if any("粉" in (v or "") for v in values):
        return False
    return any("豆" in (v or "") for v in values)


def pick_canonical_variation(variations: list[dict]) -> tuple[dict | None, int | None]:
    if not variations:
        return None, None

    def weight_key(v):
        w = variation_weight_g(v)
        return w if w is not None else float("inf")

    in_stock = [v for v in variations if v.get("is_in_stock")]
    pool = in_stock or variations
    whole_bean_pool = [v for v in pool if is_whole_bean_variation(v)] or pool
    variation = min(whole_bean_pool, key=weight_key)
    weight = variation_weight_g(variation)
    return variation, weight


def build_record(product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = product.get("permalink")
    price = product.get("prices", {}).get("price")
    price = int(price) if price is not None else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    weight_g = None
    structural_out_of_stock = not product.get("is_in_stock", True)
    if product.get("type") == "variable" and product_url:
        try:
            variations = fetch_variations(product_url)
        except requests.RequestException as e:
            print(f"[warn] バリアント取得失敗: {product_url} ({e})")
            variations = []
        variation, weight_g = pick_canonical_variation(variations)
        if variation is not None:
            structural_out_of_stock = not bool(variations) or not any(
                v.get("is_in_stock") for v in variations
            )
            if variation.get("display_price") is not None:
                price = int(variation["display_price"])

    stock_status = detect_stock_status(title, structural_out_of_stock)

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
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeepolite.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeepolite.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
