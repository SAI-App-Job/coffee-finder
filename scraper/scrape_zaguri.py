# -*- coding: utf-8 -*-
"""
scrape_zaguri.py

ザグリ珈琲(東京都杉並区阿佐谷北)の商品情報を取得する。実店舗サイト
(zaguri.tokyo、WordPress)自体には店舗案内・コーヒーの化学/焙煎/カッピングの
教育コンテンツが中心でオンラインショップ機能が無く、当初は実装不可と
判断していたが、zaguri.tokyoの「珈琲豆メニュー」ページに「当店で焙煎する
珈琲は通販でも買えます。遠方の方のために通販サイトをご用意しました→
「zaguricoffee.com」」との案内があり、別ドメイン(zaguricoffee.com、
Shopify)に実際のオンラインショップがあることが再調査で判明した
(たまじ珈琲等と同じ「情報サイトと通販サイトが別ドメイン」パターン)。

robots.txt確認済み(2026-09時点): Shopify標準の新しい記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記
(checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)。

【対象商品について】
実データ確認済み: 全10商品中、「EK43グラインダー刃留め特殊ネジセット」
「EK43 Plate Eazy Bolt /1pair」の2件はグラインダー用の交換部品でコーヒー豆
ではないため、NON_BEAN_KEYWORDSで除外する。残り8件がコーヒー豆単品。

【商品説明の構造について】
実データ確認済み: body_htmlに`<table id="tb">`という構造化テーブルがあり、
「豆名」「生産地」「農園」「標高」「品種」「精製」「テイスティングノート」
等のラベル(thタグ)と値(tdタグ)が並ぶ。ラベル表記は「：」(全角)と「:」
(半角)が商品によって混在するため、末尾の記号を正規表現で取り除いてから
辞書化する。「豆名」欄は「マンデリン」のように国名を含まない銘柄名のみの
場合と、「コロンビア エルパライソ　アナエロビックW」のように国名を含む
場合の両方があるため、産地判定はテーブル全体のテキスト(豆名+生産地+農園等)
から国名検出する方式にしている。

【重量・価格について】
実データ確認済み: variants[].gramsは全商品0固定(信頼できない、厚木珈琲・
Single O Japanと同じ問題)。variant.titleに"75g"/"150g"/"300g"のように
重量が直接入っているため、在庫があるバリエーションの中から最小重量のものを
代表バリアントとして採用する(WOODBERRY COFFEEのpick_canonical_variant()と
同じ考え方)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_processing_method,
    detect_country_name,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ザグリ珈琲",
    "url": "https://zaguricoffee.com/",
    "platform": "Shopify",
    "address": "東京都杉並区阿佐谷北1-43-6",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-09確認。Shopify標準robots.txtで"
                          "\"Public product, collection, page, blog, policy, cart, "
                          "and localized HTML is crawlable\"と明記。"
                          "checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)",
}

BASE_URL = "https://zaguricoffee.com"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["グラインダー", "Eazy Bolt"]
LABEL_PATTERN = re.compile(r"^(.+?)[:：]$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)


def fetch_products() -> list[dict]:
    all_products = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/products.json",
            params={"limit": 250, "page": page},
            headers=REQUEST_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        all_products.extend(batch)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return all_products


def parse_table_fields(body_html: str) -> dict:
    """理由はモジュールdocstring参照(table#tbのth/td行をラベル→値の辞書にする)。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    fields: dict[str, str] = {}
    table = soup.select_one("table#tb")
    if not table:
        return fields
    for row in table.select("tr"):
        th = row.select_one("th")
        td = row.select_one("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True).split()[0]
        m = LABEL_PATTERN.match(label)
        label = m.group(1) if m else label
        fields[label] = td.get_text(" ", strip=True)
    return fields


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """理由はモジュールdocstring参照(gramsフィールドが信頼できないため、
    variant.titleの"Ng"表記から重量を取得し、在庫のある最小重量を採用)。"""
    if not variants:
        return None
    in_stock = [v for v in variants if v.get("available")]
    pool = in_stock or variants

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    return min(pool, key=weight_key)


def build_record(product: dict) -> dict:
    title = (product.get("title") or "").strip()
    product_url = f"{BASE_URL}/products/{product.get('handle')}"

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    parsed = parse_product(title)
    variant = pick_canonical_variant(product.get("variants", []))
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

    body_html = product.get("body_html", "")
    fields = parse_table_fields(body_html)
    # 理由はモジュールdocstring参照(豆名欄だけでは国名を含まない場合がある
    # ため、テーブル全体のテキストから国名検出する)
    table_text = " ".join(fields.values())
    if not parsed["origin_country"]:
        country = detect_country_name(table_text) or detect_country_name(title)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    processing_raw = fields.get("精製")
    if processing_raw:
        processing_method = normalize_processing_method(processing_raw)
    else:
        detected = detect_processing_method(body_html)
        processing_method = normalize_processing_method(detected) if detected else parsed["processing_method"]

    weight_g = None
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("title") or "")
        weight_g = int(m.group(1)) if m else None

    structural_out_of_stock = not any(v.get("available") for v in product.get("variants", []))
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": fields.get("生産地") or None,
        "farm_name": fields.get("農園") or None,
        "variety": fields.get("品種") or None,
        "flavor_notes": fields.get("テイスティングノート") or None,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_products = fetch_products()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product in all_products:
        title = (product.get("title") or "").strip()
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
        variant = pick_canonical_variant(product.get("variants", []))
        current_price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title, price=current_price):
            records.append(prev)
            continue

        detail = build_record(product)
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_zaguri.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_zaguri.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
