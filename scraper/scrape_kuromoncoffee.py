# -*- coding: utf-8 -*-
"""
scrape_kuromoncoffee.py

KUROMON COFFEE(kuromon-coffee.com、〒810-0055 福岡県福岡市中央区黒門4-24、
「甘さに特化したコーヒー」を謳う自家焙煎豆専門店)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /、制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全11商品): 「焙煎セミナー」(コーヒーセミナー)・
「ドリップコーヒー体験」(ワークショップ)・「HYDRATION ステンレスボトル」
(器具)が非対象。NON_BEAN_KEYWORDSで除外する。「焙煎度別お試しセット」
(3種×80gの詰め合わせ)も単一銘柄でないため除外する。

【重量バリエーションについて】
実データ確認済み: 各銘柄が複数重量(100g/200g等)のバリアントを持つ
(gramsフィールドが0の商品もあり、その場合は商品名やvariant.titleから
重量を拾えないため未設定のままとする)。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlに対象7件全てで農園紹介・テイスティング文・
産地スペックが入っている。ただし一部商品(PDF/Wordからの変換由来と
思われる)は本文が1文字ずつ個別の<span>タグで囲まれており、単純に
get_text("\n")すると文字ごとに改行されてしまい可読性が失われることを
確認した。そのため、p/li/div/h1〜h6のうち子要素に同種のブロック要素を
持たない「末端ブロック」単位でget_text("")(区切り文字無し、同一ブロック
内の<span>分割による意図しない改行を防ぐ)を行い、ブロック間のみ改行で
連結する方式に変更した。注文/配送案内等の無関係な定型文の混入は無いため
全文をそのまま採用する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "KUROMON COFFEE",
    "url": "https://kuromon-coffee.com/",
    "platform": "Shopify",
    "address": "福岡県福岡市中央区黒門4-24",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://kuromon-coffee.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["焙煎セミナー", "ドリップコーヒー体験", "ステンレスボトル", "お試しセット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
BLOCK_TAGS = ["p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6"]


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def extract_flavor_notes(body_html: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    parts = []
    for el in soup.find_all(BLOCK_TAGS):
        if el.find(BLOCK_TAGS):
            continue
        text = el.get_text("", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts).strip() or None


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
    product_url = f"https://kuromon-coffee.com/products/{product.get('handle')}"

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
        "flavor_notes": extract_flavor_notes(product.get("body_html")),
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
    with open("data_kuromoncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kuromoncoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
