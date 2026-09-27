# -*- coding: utf-8 -*-
"""
scrape_fukucoffee.py

fuku coffee roastery(fuku-coffee-roastery.com、京都府京都市東山区大黒町
松原下ル2丁目山城町284-3、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。

【対象商品について】
実データ確認済み(/products.json全21件、2026-09時点): product_typeが
産地国名(ニカラグア・ドミニカ共和国・メキシコ・ホンジュラス・タンザニア・
グアテマラ・エチオピア・エルサルバドル・ブルンジ・インドネシア・
コロンビア・台湾・日本・ブラジル)になっており、全件がコーヒー豆単品
(非対象商品なし)。

【商品説明・重量について】
実データ確認済み: タイトルに焙煎度・重量が「/浅煎/150g」のように併記
されている。body_htmlは空、またはテイスティング文が入っている場合が
あり存在する場合のみflavor_notesとして採用する(存在しない情報を創作
しない)。variants[].gramsは実際の重量と一致するが、他店舗との統一の
ため念のためタイトル側の重量表記も採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "fuku coffee roastery",
    "url": "https://fuku-coffee-roastery.com/",
    "platform": "Shopify",
    "address": "京都府京都市東山区山城町284-3",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://fuku-coffee-roastery.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    variants = product.get("variants") or []
    whole_bean = next((v for v in variants if v.get("title") == "豆"), variants[0] if variants else None)
    if not whole_bean:
        return None
    price = int(float(whole_bean["price"]))

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": f"{BASE_URL}/products/{product['handle']}",
        }

    parsed = apply_category_hint_fallback(parsed, title)
    body_text = BeautifulSoup(product.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    stock_status = detect_stock_status(title)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else (int(whole_bean["grams"]) if whole_bean.get("grams") else None)

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
        "flavor_notes": body_text or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

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


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_fukucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
