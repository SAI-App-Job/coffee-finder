# -*- coding: utf-8 -*-
"""
scrape_customkashiwagi.py

珈巣多夢(かすたむ) 柏木店(custom-kashiwagi.com、宮城県仙台市青葉区柏木1-9-6、自家焙煎豆の通販)の
商品情報を取得する。WordPress + WooCommerce。

【取得方法】
実データ確認済み(2026-10): 公開REST API(認証不要)`/wp-json/wc/store/v1/products`から
コーヒー豆15商品(カテゴリ「コーヒー豆」、全て variable 商品)を1リクエストで取得できる。
各商品は「豆の状態(豆/挽)」×「容量(100g/200g/300g/400g/500g)」の組のバリエーションを持ち、
prices.price は最小バリエーション(豆100g)の税込価格と一致する(price_range.min_amount と同値)。
代表価格は100g(最小容量)の価格とする。在庫は is_in_stock で判定する。
ブレンドは商品名に「ブレンド」を含む商品(珈巣多夢ブレンド、モカブレンド等)。

【産地について】
店頭名が「トラジャ」「マンデリン」「エメラルドマウンテン」「キリマンジャロ」「モカ」等の
銘柄名のため、商品名から国名を判定できないものはAPIの商品説明文の産地記述で補完する。
"""

import html as htmllib
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈巣多夢 柏木店",
    "url": "https://custom-kashiwagi.com/",
    "platform": "WordPress + WooCommerce",
    "address": "宮城県仙台市青葉区柏木1-9-6",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(WooCommerce Store APIは認証不要の公開エンドポイント)",
}

API_URL = "https://custom-kashiwagi.com/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORY = "コーヒー豆"

# 銘柄名から国を補完するための対応(商品名に国名が無い場合のみ使う)
BRAND_ORIGIN = {
    "トラジャ": "インドネシア",
    "マンデリン": "インドネシア",
    "キリマンジャロ": "タンザニア",
    "エメラルドマウンテン": "コロンビア",
}


def fetch_products() -> list[dict]:
    products, page = [], 1
    while True:
        resp = requests.get(API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def min_weight_g(product: dict) -> int | None:
    weights = []
    for v in product.get("variations") or []:
        for a in v.get("attributes") or []:
            m = re.match(r"(\d+)\s*g", a.get("value") or "")
            if m:
                weights.append(int(m.group(1)))
    return min(weights) if weights else None


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        if BEAN_CATEGORY not in [c.get("name") for c in p.get("categories") or []]:
            continue
        title = re.sub(r"\s+", " ", htmllib.unescape(p["name"])).strip()
        desc_html = (p.get("short_description") or "") + (p.get("description") or "")
        desc = re.sub(r"\s+", " ", BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True))[:400] or None

        price_range = p["prices"].get("price_range") or {}
        price = int(price_range.get("min_amount") or p["prices"]["price"])
        weight = min_weight_g(p)
        available = bool(p.get("is_in_stock", True))

        parsed = parse_product(title)
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"] and desc and "産" in desc[:30]:
                detected = detect_country_name(desc[:30])
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "description"
            if not parsed["origin_country"]:
                for kw, country in BRAND_ORIGIN.items():
                    if kw in title:
                        parsed["origin_country"] = country
                        parsed["origin_source"] = "brand_name"
                        break
            parsed = apply_category_hint_fallback(parsed, title)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": p["permalink"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_customkashiwagi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_customkashiwagi.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], (r["flavor_notes"] or "")[:30])


if __name__ == "__main__":
    main()
