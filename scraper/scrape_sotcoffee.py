# -*- coding: utf-8 -*-
"""
scrape_sotcoffee.py

SOT COFFEE ROASTER(sotcoffee.com、京都府京都市東山区、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp等)で発見。大阪・天満橋/仁川に
続く3店舗目として2023年開業した京都七条店。国内3拠点のみのため
「11店舗以上の大手チェーン」基準には該当しない。

【対象カテゴリについて】
実データ確認済み(/products.json全59件、2026-09時点): product_type=
"Coffee Beans"の15件を対象とする(ストレート13・ブレンド2)。他の
ドリップバッグ・グッズ等は非対象。

【商品説明について】
実データ確認済み: body_htmlは産地・農園・標高・品種・精製方法等が
段落内の自由な散文として言及されており、コロン区切りのラベルとしては
構造化されていないため、本文全体をそのままflavor_notesとして採用する
(無理に構造化フィールドへ分離しようとすると誤抽出のリスクが高いため)。
origin_countryはタイトル(国名が英語で明記されている)から検出する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "SOT COFFEE ROASTER",
    "url": "https://www.sotcoffee.com/",
    "platform": "Shopify",
    "address": "京都府京都市東山区",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://www.sotcoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return [p for p in resp.json().get("products", []) if p.get("product_type") == "Coffee Beans"]


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    def weight_of(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")
    return min(variants, key=weight_of) if variants else None


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    variant = pick_canonical_variant(product.get("variants") or [])
    if not variant:
        return None
    price = int(float(variant["price"]))

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
    flavor_notes = BeautifulSoup(product.get("body_html") or "", "html.parser").get_text("\n", strip=True) or None
    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(variant.get("title") or "")

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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
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
    with open("data_sotcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sotcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
