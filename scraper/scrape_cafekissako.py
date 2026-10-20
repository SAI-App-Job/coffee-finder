# -*- coding: utf-8 -*-
"""
scrape_cafekissako.py

Cafe Kissako(カフェ きっさこ、福岡県行橋市高瀬302、「House Roasted Coffee」を掲げる自家焙煎の
喫茶店・店内で珈琲豆も販売)のオンラインショップ(cafekissako.com)の商品情報を取得する。
WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products)。公式サイトとECは同一ドメイン。

【対象商品】
Store API の13商品はすべて豆(variable、「グラム数」100〜500g、「豆/粉」は豆のまま/挽き3種)。
各銘柄は最小サイズ(100g)の価格(prices.price=最小価格。挽き方による価格差なし)を採用する。
在庫は is_in_stock(キューバ2種・ブルーマウンテンNo.1・ティモール オーガニックは品切れ)。
焙煎度は所属カテゴリ(浅煎り/中煎り/中深煎り/深煎り)から付与。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Cafe Kissako",
    "url": "https://cafekissako.com/",
    "platform": "WordPress + WooCommerce",
    "address": "福岡県行橋市高瀬302",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。cafekissako.com/robots.txt は wc-logs・wp-admin 等のみ禁止。Store API /wp-json は禁止対象外)",
    "source_note": "cafekissako.com の WooCommerce Store API を2026-10-20に取得。公式サイトTOP(住所・電話・営業時間・定休日)と /menu/(House Roasted Coffee、スペシャリティー豆を焙煎)を同日確認。サイトのお知らせの最終更新は2025-04-18",
    "last_verified_at": "2026-10-20",
}

API_URL = "https://cafekissako.com/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
ROAST_CATEGORIES = ("浅煎り", "中煎り", "中深煎り", "深煎り")
ORIGIN_OVERRIDES = {"ティモール": "東ティモール", "キューバ": "キューバ"}


def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(API_URL, params={"per_page": 100, "page": page}, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return products


def min_weight(p: dict) -> int | None:
    for attr in p.get("attributes") or []:
        if attr.get("name") == "グラム数":
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
    roast = next((c for c in cats if c in ROAST_CATEGORIES), None)
    weight = min_weight(p)
    if p.get("type") != "variable" or weight is None:
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
            parsed["origin_country"] = explicit
            parsed["origin_source"] = "country_name"
        if not parsed["origin_country"]:
            for kw, c in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
                    break
    desc = BeautifulSoup(p.get("short_description") or p.get("description") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", desc.replace("\xa0", " ")).strip()
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": roast,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
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
    with open("data_cafekissako.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafekissako.json に出力しました")


if __name__ == "__main__":
    main()
