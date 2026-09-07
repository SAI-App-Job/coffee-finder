# -*- coding: utf-8 -*-
"""
scrape_deaicoffee.py

DEAI COFFEE roasters(deaicoffee.com、愛知県豊田市司町1-12、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【重量バリエーションについて】
実データ確認済み: 全27商品が単一バリアント(Default Title)のみで、重量
違いの複数バリアントは持たない(1商品=1価格)。pick_canonical_variant()を
用いた最小重量選択は不要だが、他店との実装統一のため関数自体は残す。

【焙煎度について】
実データ確認済み: 商品名が「〔産地／浅煎り〕銘柄名／精選方法」または
「〔産地・中深煎り〕銘柄名／精選方法」のように区切り文字(／と・が混在)で
産地と焙煎度を併記する形式、またはブレンドは「中煎りブレンド「愛称」」の
ように先頭に焙煎度を直接埋め込む形式。いずれも浅煎り/中煎り/中深煎り/
深煎り/極深煎り という粗い表記でcoffee_parser.ROAST_KEYWORDS(プロ向け
8段階のカタカナ表記)とは粒度が異なるため、roast_hintとして保持し
roast_levelには反映しない(marutake珈琲等と同じ方針)。

【非コーヒー豆商品の除外について】
実データ確認済み(全27件): 自宅で簡単 コールドブリューコーヒーバッグ・
シングルオリジンドリップバッグ詰め合わせセットの2件が非対象。
NON_BEAN_KEYWORDSで除外する。残り25件(デカフェ2件含む)を対象とする。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "DEAI COFFEE roasters",
    "url": "https://deaicoffee.com/",
    "platform": "Shopify",
    "address": "愛知県豊田市司町1-12",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://deaicoffee.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["コールドブリューコーヒーバッグ", "ドリップバッグ詰め合わせセット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 理由はモジュールdocstring参照(長い表記を先に判定しないと「中深煎り」等が
# 「深煎り」に誤って短縮判定されてしまう)
ROAST_HINT_TERMS = ["中深煎り", "中浅煎り", "極深煎り", "浅煎り", "中煎り", "深煎り"]


def extract_roast_hint(title: str) -> str | None:
    for term in ROAST_HINT_TERMS:
        if term in title:
            return term
    return None


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
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://deaicoffee.com/products/{product.get('handle')}"

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
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": extract_roast_hint(title),
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
        if not any(kw in (p.get("title") or "") for kw in NON_BEAN_KEYWORDS)
    ]
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        product_url = f"https://deaicoffee.com/products/{product.get('handle')}"
        title = (product.get("title") or "").strip()
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
    with open("data_deaicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_deaicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
