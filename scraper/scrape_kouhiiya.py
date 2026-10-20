# -*- coding: utf-8 -*-
"""
scrape_kouhiiya.py

自家焙煎珈琲専門店こうひいや(株式会社こうひいや、福岡県大牟田市下白川町2-176、2002年創業・
5キロ釜の直火式焙煎機、店頭販売あり・日曜と第3月曜定休)のオンラインストア(ec.kouhiiya.jp)の
商品情報を取得する。WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products)。

【対象商品について】
実データ確認済み(2026-10-20): 全30商品のうち、豆の商品(variable、内容量200g/500g、ブルーマウンテンのみ
100g/500g)16件を収録する。除外: 定期購入便、ドリップバッグ、ギフトセット、リキッドコーヒー(本格ネルドリップ
抽出)、カフェオレベース、器具(キャニスター)。
各銘柄は「内容量」属性の最小サイズと、その最小サイズ価格(Store APIの prices.price=最小価格、豆のまま/
挽き方で価格差なし)を採用。在庫は is_in_stock。焙煎度は商品URLのカテゴリ(light=浅煎り/midium=中煎り/
dark=深煎り)または説明文から付与する。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "こうひいや",
    "url": "https://ec.kouhiiya.jp/",
    "platform": "WordPress + WooCommerce",
    "address": "福岡県大牟田市下白川町2-176",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。ec.kouhiiya.jp/robots.txt は wc-logs・wp-admin・add-to-cart のみ禁止。Store API /wp-json は禁止対象外)",
    "source_note": "ec.kouhiiya.jp の WooCommerce Store API を2026-10-20に取得。公式サイト kouhiiya.jp/about(5キロ釜の直火式焙煎機・自家焙煎珈琲専門店)と kouhiiya.jp/shop(住所・定休日・小売)を同日確認",
    "last_verified_at": "2026-10-20",
}

API_URL = "https://ec.kouhiiya.jp/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2

# 商品URLのカテゴリ(/product/<cat>/...)から焙煎度。ice は説明文から個別指定
URL_ROAST = {"light": "浅煎り", "midium": "中煎り", "dark": "深煎り"}
BEAN_URL_CATS = ("light", "midium", "dark", "ice")
# アイスコーヒー専用 アイスMIX(説明文「こうひいやオリジナルブレンドの極深煎り」)
ROAST_OVERRIDES = {537: "極深煎り"}
BLEND_NAMES = ("ブレンド", "MIX")


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
        if attr.get("name") == "内容量":
            ws = []
            for t in attr.get("terms") or []:
                m = re.match(r"^\s*(\d+)\s*g", t.get("name", ""))
                if m:
                    ws.append(int(m.group(1)))
            if ws:
                return min(ws)
    return None


def url_category(p: dict) -> str | None:
    m = re.search(r"/product/([^/]+)/", p["permalink"])
    return m.group(1) if m else None


def build_record(p: dict) -> dict | None:
    if p.get("type") != "variable":
        return None
    name = html.unescape(p["name"]).strip()
    name = re.sub(r"\s+", " ", name.replace("　", " "))
    if "定期購入" in name:
        return None
    cat = url_category(p)
    if cat not in BEAN_URL_CATS:
        return None
    weight = min_weight(p)
    if weight is None:
        return None
    parsed = parse_product(name)
    is_blend = any(k in name for k in BLEND_NAMES)
    if is_blend:
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
    desc = BeautifulSoup(p.get("description") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", desc.replace("\xa0", " ")).strip()
    roast = ROAST_OVERRIDES.get(p["id"]) or URL_ROAST.get(cat) or parsed["roast_level"]
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
        "roast_level": roast,
        "roast_hint": URL_ROAST.get(cat),
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
    with open("data_kouhiiya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kouhiiya.json に出力しました")


if __name__ == "__main__":
    main()
