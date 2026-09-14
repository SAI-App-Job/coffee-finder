# -*- coding: utf-8 -*-
"""
scrape_azumacoffee.py

東珈琲店(azumacoffee.com、広島県福山市城見町2-5-17、アジアのスペシャルティ
コーヒー専門の自家焙煎豆オンライン販売)の商品情報を取得する。Shopify
(/products.json全件取得方式)。

【住所について】
特定商取引法ページ(https://azumacoffee.com/policies/legal-notice)を
実データ確認したところ、「住所」欄には運営会社(ONSAYA COFFEE、岡山県
岡山市北区奉還町2-9-1)の登記上の住所が記載されている一方、「販売所住所」
欄には「福山市城見町2-5-17」(候補リストの住所と一致)が別途明記されている。
本プロジェクトでは実際の販売拠点である「販売所住所」を採用する
(BASE COFFEE南あわじ市・倉敷珈琲館と同種のケース。運営会社の登記住所と
実店舗所在地が異なる)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /、
制限なし。

【商品構成について】
実データ確認済み(全20件): コーヒー豆単品8銘柄(ネパール×3・スマトラ×2・
パプアニューギニア×1・東ティモール×1・アジアンブレンド2026×1、いずれも
200g/400g/1kgの3種の重量バリエーション)と、非対象の「ドリップバッグ」
各種(単品10g・ギフトセット)、「台湾嘉義瑞峰 烏龍茶」(コーヒーではなく
台湾烏龍茶)、「焙煎士アズマのお試しセット」(3種詰め合わせ、単一銘柄でない)、
「珈琲豆ギフトセット(2袋入り)」(複数銘柄詰め合わせ)。NON_BEAN_KEYWORDSで
除外する。

【重量について】
実データ確認済み: 対象8銘柄はいずれもバリアントのoption1に「200g」
「400g(-¥216)」「1kg(-¥864)」の3種類の重量・値引き表記があり、最小重量
(200g)を代表として採用する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "東珈琲店",
    "url": "https://azumacoffee.com/",
    "platform": "Shopify",
    "address": "広島県福山市城見町2-5-17",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://azumacoffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照
NON_BEAN_KEYWORDS = ["ドリップバッグ", "烏龍茶", "お試しセット", "ギフトセット"]
WEIGHT_PATTERN_KG = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE)
WEIGHT_PATTERN_G = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(title: str) -> bool:
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def parse_weight_g(option_text: str) -> int | None:
    m = WEIGHT_PATTERN_KG.search(option_text)
    if m:
        return int(float(m.group(1)) * 1000)
    m = WEIGHT_PATTERN_G.search(option_text)
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def weight_key(v):
        w = parse_weight_g(v.get("option1") or "")
        return w if w is not None else float("inf")

    return sorted(variants, key=weight_key)[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or is_excluded(title):
        return None

    parsed = parse_product(title)
    product_url = f"https://azumacoffee.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

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

    weight_g = parse_weight_g(variant.get("option1") or "") if variant else None
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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_azumacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_azumacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
