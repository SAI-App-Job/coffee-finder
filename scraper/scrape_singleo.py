# -*- coding: utf-8 -*-
"""
scrape_singleo.py

Single O Japan(シングルオー、singleo.jp)の商品情報を取得する。オーストラリア
発のロースタリーブランドで、日本国内に複数店舗(有楽町・両国)があるうち、
両国の焙煎所(SINGLE O RYOGOKU ROASTWORKS/CAFE、東京都墨田区亀沢)で
毎週焙煎した豆をオンラインショップ(Shopify、全店舗共通の単一ストア)で
販売している。

robots.txt確認済み(2026-09時点): Shopify標準の新しい記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記
(checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)。

【対象商品について】
実データ確認済み: カテゴリ(collections)は「1kg」「250g」等の重量別・
「ALL ITEMS」「NEW」等の横断ビューが多く重複が激しいため、Coffee Roast SAIと
同じく/products.json(全件)を使い、product_typeでフィルタする。全52件中、
"BLEND - ブレンド"(8件)・"SINGLE ORIGIN - シングルオリジン"(6件)・
"DECAF - ディカフェ"(3件)の3タイプ(計17件)がコーヒー豆単品を指す。
"PARACHUTE - ドリップバック"・"MERCH - グッズ"・"SPECIAL SET - スペシャル
セット"・"TEA - お茶"・"EQUIPMENT - 抽出器具"は対象外。

【重量について】
実データ確認済み: variants[].gramsは全商品0固定(信頼できない、厚木珈琲と
同じ問題)。商品名自体に重量表記(「150g」「250g」「1kg」)が含まれるため、
そちらから正規表現で取得する(kg表記は1000倍してg換算)。

【ブレンドの産地(CURRENT ORIGINS)について】
実データ確認済み: ブレンド商品のbody_htmlには「現在のオリジン／CURRENT
ORIGINS:」という構造化欄があり、直後のdiv内に国名(英語表記)が子divとして
複数列挙される(例:YEEHAH!ブレンドはINDONESIA・COSTA RICAの2ヶ国)。自由
記述からdetect_country_name()で1ヶ国だけ拾う方式では、最初に文中で言及
された国しか取れず、実際には2ヶ国以上の配合であるブレンドの産地情報が
不正確になっていた(実ワークフロー実行後のデータ検証で発覚)。この構造化欄を
優先的にパースし、複数国あればblend_componentsに格納、origin_countryは
null(ブレンドは単一国のフィールドに収まらないため)とする。欄自体はあっても
値が空の商品(例:AWOL DECAFブレンド)は収穫期により産地非開示のため、その
まま何も設定しない。

【バリエーションについて】
実データ確認済み: 全商品ともバリエーションは「WHOLE BEAN／豆」「PAPER
FILTER／粉」(挽き方)の2種のみで、重量は商品名ごとに固定・別商品(価格も
共通)。挽き方によって価格が変わらないため、最初のバリアントの価格を
そのまま採用する。
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
    "name": "Single O Japan",
    "url": "https://singleo.jp/",
    "platform": "Shopify",
    "address": "東京都墨田区亀沢3-21-5",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-09確認。Shopify標準robots.txtで"
                          "\"Public product, collection, page, blog, policy, cart, "
                          "and localized HTML is crawlable\"と明記。"
                          "checkout/paymentの自動化のみ禁止、本スクレイパーは対象外)",
}

BASE_URL = "https://singleo.jp"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPES = {
    "BLEND - ブレンド": "ブレンド",
    "SINGLE ORIGIN - シングルオリジン": "シングルオリジン",
    "DECAF - ディカフェ": "デカフェ",
}

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.IGNORECASE)


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


def parse_weight_from_title(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    if not m:
        return None
    value = float(m.group(1))
    grams = value * 1000 if m.group(2).lower() == "kg" else value
    return int(grams)


def build_record(product: dict, category_hint: str) -> dict:
    title = (product.get("title") or "").strip()
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    variants = product.get("variants") or [{}]
    variant = variants[0]
    price = int(float(variant["price"])) if variant.get("price") is not None else None

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

    body_soup = BeautifulSoup(product.get("body_html", ""), "html.parser")
    body_text = body_soup.get_text(" ")
    is_blend = parsed["category"] == "ブレンド"

    blend_components: list[dict] = []
    if is_blend:
        # 理由はモジュールdocstring参照。ブレンド商品は「現在のオリジン／
        # CURRENT ORIGINS:」という構造化欄(国名を子divで列挙、複数国あれば
        # 複数div)を持つため、これを優先的に使う(自由記述の産地判定では
        # 最初に見つかった1ヶ国しか拾えず、実際には2ヶ国以上の配合である
        # 実例(YEEHAH!ブレンド:INDONESIA+COSTA RICA)を取りこぼしていた)。
        # 欄自体はあっても値が空の商品もある(例:AWOLブレンド、収穫期により
        # 産地非開示)。
        for div in body_soup.find_all("div"):
            if "ORIGINS" in div.get_text(strip=True).upper():
                next_div = div.find_next_sibling("div")
                if next_div:
                    for child in next_div.find_all("div"):
                        raw_value = child.get_text(strip=True)
                        country = detect_country_name(raw_value)
                        if country:
                            blend_components.append({"origin_country": country, "percentage": None})
                break
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            country = detect_country_name(body_text)
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, category_hint)

    detected_processing = detect_processing_method(body_text)
    if detected_processing:
        processing_method = normalize_processing_method(detected_processing)
    else:
        processing_method = parsed["processing_method"]

    structural_out_of_stock = not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": price,
        "weight_g": parse_weight_from_title(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_products = fetch_products()
    targets = [p for p in all_products if p.get("product_type") in TARGET_PRODUCT_TYPES]

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        title = (product.get("title") or "").strip()
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
        variant = (product.get("variants") or [{}])[0]
        current_price = int(float(variant["price"])) if variant.get("price") is not None else None

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title, price=current_price):
            records.append(prev)
            continue

        category_hint = TARGET_PRODUCT_TYPES[product["product_type"]]
        detail = build_record(product, category_hint)
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_singleo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_singleo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
