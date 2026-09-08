# -*- coding: utf-8 -*-
"""
scrape_elmersgreen.py

エルマーズグリーンカフェ / EMBANKMENT Coffee(elmersgreen.com、大阪市中央区
北浜1丁目1-23 1F〈エンバンクメントコーヒー 北浜〉、自家焙煎豆のオンライン
販売。運営は株式会社カフーツ、堺市中区に本店(エルマーズグリーンコーヒー
アンドベイクス 堺)を含め大阪市内外に計5拠点)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

店舗一覧は/pages/stores-locationsで確認: ①エルマーズグリーンコーヒー
アンドベイクス 堺(堺市中区東山765-1)、②エルマーズグリーンカフェ 北浜
(大阪市中央区高麗橋1-7-3 北浜プラザ1階)、③エンバンクメントコーヒー 北浜
(大阪市中央区北浜1丁目1-23 1F)、④喫茶室KOHORO(大阪市北区梅田1-13-13
阪神百貨店7F)の4拠点住所が明記されている(5拠点目は焙煎工房等と推定)。
商品自体はEMBANKMENT Coffeeブランドの単品ロットが中心のため、
EMBANKMENT Coffee 北浜の住所を採用。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全24商品中、product_type="beans"は14件。ただしこの
中にもドリップバッグ(個包装)・お試し詰め合わせセット(複数銘柄アソート)
が混在するため、TARGET_PRODUCT_TYPE="beans"に加えてNON_BEAN_KEYWORDSで
二重に除外する。product_type="foods"(ラスク・グラノーラ)・"tool"
(HARIO製ドリッパー/ミル/スケール)・"packs"(ドリップバッグ個数セット)・
"subscription"(Roaster's選定の定期便的商品)・空欄(コホロ喫茶カウンターの
時間帯予約枠、商品ではない)は対象外。

【非コーヒー豆商品の除外について】
実データ確認済み: 「Drip Bag『POSTMAN / 季節のブレンド』」(ドリップバッグ、
個包装)・「【オンライン限定】ELMERS GREEN＆EMBANKMENT Coffee お試し5種類
セット」「【オンライン限定】EMBANKMENT Coffee お試し3種類セット」(いずれも
複数銘柄の詰め合わせで単一銘柄と特定できない)が非対象。NON_BEAN_KEYWORDSで
除外する。

【重量バリエーションについて】
実データ確認済み: 各銘柄が200g/500gの2バリアントを持つ。variants配列の
gramsから最小重量(200g)を代表として採用する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "エルマーズグリーン / EMBANKMENT Coffee",
    "url": "https://elmersgreen.com/",
    "platform": "Shopify",
    "address": "大阪府大阪市中央区北浜1丁目1-23 1F",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://elmersgreen.com/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "beans"
NON_BEAN_KEYWORDS = ["ドリップバッグ", "Drip Bag", "お試し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


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
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://elmersgreen.com/products/{product.get('handle')}"

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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    targets = [
        p for p in products
        if p.get("product_type") == TARGET_PRODUCT_TYPE
        and not any(kw in (p.get("title") or "") for kw in NON_BEAN_KEYWORDS)
    ]
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        product_url = f"https://elmersgreen.com/products/{product.get('handle')}"
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
    with open("data_elmersgreen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_elmersgreen.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
