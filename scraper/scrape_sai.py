# -*- coding: utf-8 -*-
"""
scrape_sai.py

Coffee Roast SAI(コーヒーロースト サイ、coffeeroastsai.com、東京都港区高輪、
2006年創業)の商品情報を取得する。Shopify(WOODBERRY COFFEE・厚木珈琲・豆善と
同じプラットフォーム)。

robots.txt確認済み(2026-09時点): Shopify標準の新しい記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記
(checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)。

【対象商品について】
実データ確認済み: カテゴリ(collections)はすべて「マイルド系」「苦味系」等の
味わい別の横断的な分類(MARUTAKE COFFEE BEANSの「Taste」カテゴリと同種の
重複ビュー)のため、collections単位ではなく/products.json(全件)を使う。
全37件中、product_typeが空文字列の「送料差額（ヤマト宅急便）」1件のみが
非コーヒー豆(送料調整用のダミー商品)で、他36件はすべてproduct_type
「豆」または「オススメ」のコーヒー豆単品。

【商品説明の構造について】
実データ確認済み: body_htmlに2種類のラベル形式が混在する。前半は
「味の傾向：マイルド」「オススメロースト：シティ2」のようにラベルと
コロンの間にスペースが無く、後半の「詳細情報」以降は「国名　　　：コロンビア」
のように全角スペースでパディングされている。どちらの形式にもマッチする
正規表現(LABEL_PATTERN)で統一的に抽出する。「オススメロースト」は
「シティ2」のように店独自の数値付き表記でROAST_LEVELSの8段階とは異なるため、
roast_hintとして保持しroast_levelには反映しない。

【ブレンドの産地判定について】
実データ確認済み: ブレンド商品の「国名」欄は「主にインドネシアカロシトラジャ、
ブラジルショコラ、メキシコ有機栽培」のように「、」区切りの自由記述(隠房と
似た形式)。たまじ珈琲・MARUTAKE COFFEE BEANSと同じく「、」で分割し各断片を
detect_country_name()に通して国名を検出、判明した国の数でブレンド/ストレート
を判定する(0〜1件ならストレート、2件以上ならブレンド。商品名の「ブレンド」
表記が無くても判定できる)。

【重量・価格について】
実データ確認済み: 全商品ともバリアントは単一(Default Title)で、
variants[0].gramsに正しい重量(g)が入っている(厚木珈琲のgrams=0固定問題は
無い)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Coffee Roast SAI",
    "url": "https://coffeeroastsai.com/",
    "platform": "Shopify",
    "address": "東京都港区高輪1-21-3 チバビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-09確認。Shopify標準robots.txtで"
                          "\"Public product, collection, page, blog, policy, cart, "
                          "and localized HTML is crawlable\"と明記。"
                          "checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)",
}

BASE_URL = "https://coffeeroastsai.com"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["送料差額"]

# 理由はモジュールdocstring参照(ラベル前後の全角スペースの有無どちらにも対応)
LABEL_PATTERN = re.compile(r"^([^\s：:]+)[\s　]*[：:]\s*(.+)$")


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


def parse_label_fields(body_html: str) -> dict:
    soup = BeautifulSoup(body_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    labels: dict[str, str] = {}
    for p in soup.select("p"):
        for line in p.get_text().split("\n"):
            line = line.strip()
            m = LABEL_PATTERN.match(line)
            if m:
                labels[m.group(1).strip()] = m.group(2).strip()
    return labels


def build_record(product: dict) -> dict:
    title = (product.get("title") or "").strip()
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    variant = (product.get("variants") or [{}])[0]
    price = int(float(variant["price"])) if variant.get("price") is not None else None

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    parsed = parse_product(title)

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

    labels = parse_label_fields(product.get("body_html", ""))

    origin_raw = labels.get("国名")
    origin_countries: list[str] = []
    if origin_raw:
        for part in re.split(r"[、,]", origin_raw):
            country = detect_country_name(part)
            if country and country not in origin_countries:
                origin_countries.append(country)

    # 理由はモジュールdocstring参照(「国名」欄で判明した国の数を優先し、
    # 0件の場合のみ商品名解析(parse_product)の判定にフォールバックする)
    if len(origin_countries) >= 2:
        is_blend = True
    elif len(origin_countries) == 1:
        is_blend = False
    else:
        is_blend = parsed["category"] == "ブレンド"
    parsed["category"] = "ブレンド" if is_blend else "ストレート"

    blend_components = []
    origin_country, origin_source = None, None
    if is_blend:
        blend_components = [{"origin_country": c, "percentage": None} for c in origin_countries]
    else:
        if origin_countries:
            origin_country, origin_source = origin_countries[0], "product_description"
        else:
            origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

    parsed = apply_category_hint_fallback(parsed, None)
    if not origin_country:
        origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

    processing_method = None
    processing_raw = labels.get("精製方法")
    if processing_raw:
        processing_method = normalize_processing_method(processing_raw)
    elif parsed["processing_method"]:
        processing_method = parsed["processing_method"]

    structural_out_of_stock = not (product.get("variants") and
                                    any(v.get("available") for v in product["variants"]))
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": origin_country,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(店独自の数値付き表記のためroast_hintに保持)
        "roast_hint": labels.get("オススメロースト"),
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": labels.get("エリア") or None,
        "variety": labels.get("豆の種類") or None,
        "farm_name": labels.get("農園") or None,
        "blend_components": blend_components,
        "price": price,
        "weight_g": variant.get("grams"),
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
        variant = (product.get("variants") or [{}])[0]
        current_price = int(float(variant["price"])) if variant.get("price") is not None else None

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
    with open("data_sai.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sai.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
