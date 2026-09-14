# -*- coding: utf-8 -*-
"""
scrape_novoldcoffee.py

NOVOLD COFFEE ROASTERS(novold-coffee.com、〒770-0873 徳島県徳島市東沖洲
2丁目26-12、自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify
(/products.json全件取得方式)。

【住所について】
実データ確認済み(2026-09時点): 公式サイトの特定商取引法ページ
(https://novold-coffee.com/pages/tokuteishotorihiki)で「〒770-0873
徳島県徳島市東沖洲2丁目26-12」と一致確認済み。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全18件): 各銘柄の「定期コース」(サブスクリプション、
handle末尾"-sub")・飲み比べセット お好きな3種(各200g、産地不定のアソート)・
お試しパック お好きな3種(各100g、同上)・NOVOLDドリップバッグ(8カップ入り/
4カップ入り)が非対象。NON_BEAN_KEYWORDSで除外し、"-sub"のhandleも除外する。
残り7銘柄(ストレート6種+ノボルドエスペシャル1種)が対象。

【重量違いの重複について】
実データ確認済み: 各銘柄が200g/500gの2サイズ×挽き方5種(豆のまま/中挽き/
粗挽き/中細挽き/細挽き、価格は挽き方に依らず重量ごとに同一)のバリアント
構成。商品名自体には重量表記が無いため、Shopifyのvariants側から最小重量
(200g)の代表バリアントを選んで価格を採用する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

VARIANT_WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

SHOP_INFO = {
    "name": "NOVOLD COFFEE ROASTERS",
    "url": "https://novold-coffee.com/",
    "platform": "Shopify",
    "address": "徳島県徳島市東沖洲2丁目26-12",
    "prefecture": "徳島県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://novold-coffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["飲み比べセット", "お試しパック", "ドリップバッグ", "定期コース"]


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(product: dict) -> bool:
    title = (product.get("title") or "").strip()
    handle = (product.get("handle") or "").strip()
    if not title:
        return True
    if handle.endswith("-sub"):
        return True
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def weight_from_variant(variant: dict) -> int | None:
    # 理由はモジュールdocstring参照。実データ確認済み: このShopifyストアは
    # variants[].gramsが常に0で信頼できないため、バリアントのtitle
    # (例: "200g / 豆のまま")から重量を取得する。
    m = VARIANT_WEIGHT_PATTERN.search(variant.get("title") or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """理由はモジュールdocstring参照(重量×挽き方のバリアントから、
    最小重量・かつ「豆のまま」を優先して代表バリアントを選ぶ)。"""
    if not variants:
        return None

    def weight_of(v: dict) -> float:
        return weight_from_variant(v) or float("inf")

    min_weight = min(weight_of(v) for v in variants)
    same_weight = [v for v in variants if weight_of(v) == min_weight]
    whole_bean = [v for v in same_weight if "豆のまま" in (v.get("title") or "")]
    return (whole_bean or same_weight)[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    parsed = parse_product(title)
    product_url = f"https://novold-coffee.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
    weight_g = weight_from_variant(variant) if variant else None

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

    same_weight_variants = [v for v in variants if weight_from_variant(v) == weight_g]
    check_variants = same_weight_variants or variants
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
    filtered = [p for p in products if not is_excluded(p)]

    records = []
    flavored_records = []
    for product in filtered:
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
    with open("data_novoldcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_novoldcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
