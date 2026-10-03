# -*- coding: utf-8 -*-
"""
scrape_cafebach.py

カフェ・バッハ(cafe Bach、bach-kaffee.co.jp、東京都台東区日本堤1-23-9、1968年創業・店舗は
山谷の本店1店舗、運営は株式会社バッハコーヒー、田口護氏の自家焙煎店)のオンラインショップの
商品情報を取得する。WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products)。

【対象商品について】
実データ確認済み(2026-10時点): オンラインショップのカテゴリ「コーヒー豆」配下の
「深煎り」「中深煎り」「中煎り」「浅煎り」「ブレンド」のいずれかに属する商品のみを収録する
(ストレート20・ブレンド4)。焼き菓子・器具・書籍・グッズ・ギフト・オプションは除外。
価格は2026-04-30に改定済み(コーヒーの価格改定について、2026-03-29告知)で、サイトの
「コーヒー豆」ページ・オンラインショップとも改定後価格(バッハブレンド100g 1,000円等)。

【重量・価格・在庫】
各商品の「グラム数」属性(50g/100g/200g)の最小サイズと、その最小サイズ価格
(Store APIのprices.price=最小価格)を採用する(パナマ・ドンパチ ゲイシャ ナチュラルと
ブルーマウンテンNo.1は50g販売あり)。在庫は is_in_stock。焙煎度は所属カテゴリ
(深煎り〜浅煎り)から roast_hint として保持する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェ・バッハ",
    "url": "https://www.bach-kaffee.co.jp/",
    "platform": "WordPress + WooCommerce",
    "address": "東京都台東区日本堤1-23-9",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

API_URL = "https://www.bach-kaffee.co.jp/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_CATEGORIES = ("深煎り", "中深煎り", "中煎り", "浅煎り")
BEAN_CATEGORIES = ROAST_CATEGORIES + ("ブレンド",)
ORIGIN_OVERRIDES = {"インディア": "インド", "ハイチ": "ハイチ"}


def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(API_URL, params={"per_page": 100, "page": page}, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 400:  # 範囲外のページ
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def min_weight(p: dict) -> int | None:
    for attr in p.get("attributes") or []:
        if attr.get("taxonomy") == "pa_bean-size" or attr.get("name") == "グラム数":
            ws = []
            for t in attr.get("terms") or []:
                m = re.match(r"^\s*(\d+)\s*g", t.get("name", ""))
                if m:
                    ws.append(int(m.group(1)))
            if ws:
                return min(ws)
    return None


def build_record(p: dict) -> dict | None:
    cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
    if not any(c in BEAN_CATEGORIES for c in cats):
        return None
    name = html.unescape(p["name"]).strip()
    name = re.sub(r"\s+", " ", name.replace("　", " "))
    parsed = parse_product(name)
    if "ブレンド" in cats or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        explicit = detect_country_name(name)
        if explicit and explicit != parsed["origin_country"]:
            # 「イエメン・モカハラーズ」のように、銘柄名(モカ=エチオピア)より名前中の国名表記を優先する
            parsed["origin_country"] = explicit
            parsed["origin_source"] = "country_name"
        if not parsed["origin_country"]:
            for kw, c in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
                    break
        if not parsed["origin_country"]:
            c = detect_country_name(BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)[:100])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
    desc = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", desc.replace("\xa0", " ")).strip()
    roast = next((c for c in cats if c in ROAST_CATEGORIES), None)
    price_info = p.get("prices") or {}
    price = int(price_info.get("price")) if price_info.get("price") else None
    in_stock = bool(p.get("is_in_stock"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": min_weight(p),
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafebach.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafebach.json に出力しました")


if __name__ == "__main__":
    main()
