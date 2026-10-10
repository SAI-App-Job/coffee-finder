# -*- coding: utf-8 -*-
"""
scrape_kokage.py

珈琲豆焙煎 こかげ(cafe-kokage.com、長野県中野市新保935-2)のオンラインショップの
商品情報を取得する。WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products)。

【対象商品】カテゴリ「ストレートコーヒー」(6点)「ブレンドコーヒー」(4点)の計10点のみ。
ギフトボックス・ギフトセット・ドリップバッグ・フィルターペーパー等の関連商品は除外。
【重量・価格】各商品は「豆の状態」×「グラム(100g/200g/500g)」のバリエーション商品。
最小の100gの価格(Store APIのprices.price=最小価格。商品ページの「価格：○○円/100g」と一致)を採用。
【産地・焙煎度】商品ページ説明欄の「ロースト：」「精製方法：」「商品説明：」から取得。
商品名の「*売り切れ*」表記は取り除き、在庫は Store API の is_in_stock を採用する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆焙煎 こかげ",
    "url": "https://cafe-kokage.com/products/",
    "platform": "WordPress + WooCommerce",
    "address": "長野県中野市新保935-2",
    "prefecture": "長野県",
    "robots_txt_status": "未確認",
}

API_URL = "https://cafe-kokage.com/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORIES = ("ストレートコーヒー", "ブレンドコーヒー")


def fetch_products():
    products, page = [], 1
    while True:
        r = requests.get(API_URL, params={"per_page": 100, "page": page}, headers=HEADERS, timeout=30)
        if r.status_code == 400:
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def page_info(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
    i = text.find("追加情報")
    j = text.find("【豆のまま】")
    seg = text[i:j] if i >= 0 and j > i else text
    info = {}
    m = re.search(r"ロースト：\s*(\S+)", seg)
    info["roast"] = m.group(1) if m else None
    m = re.search(r"精製方法：\s*(\S+)", seg)
    info["process"] = m.group(1) if m else None
    m = re.search(r"商品説明：\s*(.+?)(?=\n(?:ロースト|苦味)：|\n苦味|$)", seg, re.S)
    info["desc"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    m = re.search(r"価格：\s*([\d,]+)円\s*/\s*(\d+)\s*[gｇ]", seg)
    info["price100"] = int(m.group(1).replace(",", "")) if m else None
    info["w"] = int(m.group(2)) if m else None
    return info


def build_record(p):
    cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
    if not any(c in BEAN_CATEGORIES for c in cats):
        return None
    raw = html.unescape(p["name"])
    name = re.sub(r"<[^>]+>", "", raw).replace("*売り切れ*", "").replace("　", " ")
    name = re.sub(r"\s+", " ", name).strip()
    info = page_info(p["permalink"])
    parsed = parse_product(name)
    if "ブレンドコーヒー" in cats or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        c = detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    price = int(p["prices"]["price"]) if p["prices"].get("price") else None
    if info["price100"] and price and info["price100"] != price:
        print("[warn] price mismatch", name, price, info["price100"])
    in_stock = bool(p.get("is_in_stock"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or info["process"],
        "grade": parsed["grade"],
        "roast_level": info["roast"] or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": (info["desc"] or "")[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": info["w"] or 100,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def scrape_all_products():
    out = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            out.append(rec)
    return out


def main():
    records = scrape_all_products()
    with open("data_kokage.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kokage.json に出力しました")


if __name__ == "__main__":
    main()
