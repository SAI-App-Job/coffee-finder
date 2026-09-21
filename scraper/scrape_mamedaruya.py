# -*- coding: utf-8 -*-
"""
scrape_mamedaruya.py

豆樽屋珈琲(mamedaruya.com、広島県広島市中区羽衣町1-25-108、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json全件取得方式)。

【住所について】
候補リストでは「広島県広島市中区富士見町16-4 セイコウビル101」とされて
いたが、公式ストアの特定商取引法ページ(https://mamedaruya.com/policies/
legal-notice)で実データ確認したところ「〒730-0814 広島県広島市中区羽衣町
1-25-108」であることを確認した(2026-09時点)。候補リストの住所は古い情報と
判断し、この実データを採用する。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /、
制限なし。

【商品構成について】
実データ確認済み(全18件): コーヒー豆単品(季節のブレンド・Mild#1〜#3・
エスプレッソブレンド・Rich#1・Rich#3・コクのブレンド・豆樽屋ブレンドの
8銘柄)と、非対象の「コーヒーバッグ」「ドリップバッグ」各種(単品/5+1個
セット、複数銘柄詰め合わせのMixセットを含む)、「お試しセット」(3銘柄の
挽き方違い詰め合わせ、単一銘柄でないため非対象)。NON_BEAN_KEYWORDSで除外
する。

【バリアント構造について】
実データ確認済み: 各銘柄はoption1=挽き方(豆のまま/中挽き/粗挽き（おすすめ）
等)、option2=重量(100g/150g)の組み合わせ。挽き方によらず同一重量なら同一
価格のため、option1="豆のまま"(未挽きの豆)かつ最小重量(100g)のバリアントを
代表として採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlは冒頭が支払い/配送案内・お試しセット案内の
リンクで始まるが、対象9件全てにその後「＜味わい＞」(ストレート豆)または
「＜ブレンドコンセプト＞」(ブレンド)という見出しから始まるテイスティング
文・商品説明・農園情報が続くことを確認した。この開始見出しから
「＜カテゴリー＞」見出し直前までを抽出する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆樽屋珈琲",
    "url": "https://mamedaruya.com/",
    "platform": "Shopify",
    "address": "広島県広島市中区羽衣町1-25-108",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://mamedaruya.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照
NON_BEAN_KEYWORDS = ["コーヒーバッグ", "ドリップバッグ", "お試しセット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_START_PATTERN = re.compile(r"＜(?:ブレンドコンセプト|味わい)")
FLAVOR_STOP_PATTERN = re.compile(r"＜カテゴリー＞")


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not body_html:
        return None
    soup = BeautifulSoup(body_html, "html.parser")
    text = soup.get_text("\n", strip=True)
    start_m = FLAVOR_START_PATTERN.search(text)
    if not start_m:
        return None
    text = text[start_m.start():]
    stop_m = FLAVOR_STOP_PATTERN.search(text)
    if stop_m:
        text = text[:stop_m.start()]
    return text.strip() or None


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(title: str) -> bool:
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if (v.get("option1") or "") == "豆のまま"]
    pool = whole_bean or variants

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("option2") or "")
        return int(m.group(1)) if m else float("inf")

    pool = sorted(pool, key=weight_key)
    return pool[0] if pool else None


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or is_excluded(title):
        return None

    parsed = parse_product(title)
    product_url = f"https://mamedaruya.com/products/{product.get('handle')}"

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

    weight_g = None
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("option2") or "")
        weight_g = int(m.group(1)) if m else None

    whole_bean_variants = [v for v in variants if (v.get("option1") or "") == "豆のまま"]
    check_variants = whole_bean_variants or variants
    all_out_of_stock = bool(check_variants) and not any(v.get("available") for v in check_variants)
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

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mamedaruya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamedaruya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
