# -*- coding: utf-8 -*-
"""
scrape_amanocoffee.py

AMANO COFFEE ROASTERS(amano-coffee.com、京都府京都市北区紫竹東高縄町
23-2 ルピナス1F、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。

【対象商品について】
実データ確認済み(/products.json全24件、2026-09時点): 全商品がproduct_type
="コーヒー"だが、うち12件はドリップバッグ(5袋入り)・水出しアイス
コーヒーパック・お試し用ドリップバッグセットで、コーヒー豆単品とは
形態が異なるためNON_BEAN_KEYWORDSで除外。残り12件がバリアント
「豆/100g・250g・500g」を持つコーヒー豆単品(ストレート8・ブレンド4)。

【商品説明について】
実データ確認済み: body_htmlは全商品で「ご注文後、7〜10日前後の発送に
なります」という発送案内の定型文のみで、テイスティング等の記述が
一切無い。存在しない情報を創作しないためflavor_notesはnullのままとする。
ブレンドは商品名に原産国が「【グァテマラ・ブラジル】」のように併記
されているため、farm_noteとして原産国リストを保持する。
"""

import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "AMANO COFFEE ROASTERS",
    "url": "https://amano-coffee.com/",
    "platform": "Shopify",
    "address": "京都府京都市北区紫竹東高縄町23-2 ルピナス1F",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://amano-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "アイスコーヒー", "エントリーセレクト"]
BRACKET_PATTERN = re.compile(r"【([^】]*)】")


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    variants = product.get("variants") or []
    bean_variant = next((v for v in variants if (v.get("title") or "").startswith("豆")), None)
    if not bean_variant:
        return None
    price = int(float(bean_variant["price"]))
    weight_m = re.search(r"(\d+)\s*[gｇ]", bean_variant.get("title") or "")
    weight_g = int(weight_m.group(1)) if weight_m else 100

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
    origin_note = "、".join(BRACKET_PATTERN.findall(title))
    farm_note = f"原産国：{origin_note}" if origin_note and parsed["category"] == "ブレンド" else None
    stock_status = detect_stock_status(title)

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
        "flavor_notes": None,
        "farm_note": farm_note,
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
    with open("data_amanocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amanocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
