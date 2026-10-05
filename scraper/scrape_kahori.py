# -*- coding: utf-8 -*-
"""
scrape_kahori.py

かほり(www.kahori.biz、福岡県那珂川市五郎丸2-42-1の自家焙煎珈琲店)の商品情報を取得する。
WooCommerce(Store API `/wp-json/wc/store/v1/products`)。

【対象商品について】
実データ確認済み(2026-10時点): Store APIの全20商品(カテゴリ「珈琲豆」+焙煎度別カテゴリ
「中煎り」「中深煎り」「深煎り」)はすべて焙煎豆(ブレンド・ストレート)で、全て可変商品
(内容量100g/200g/500g × 挽き方3種)。セット・ギフト・ドリップバッグ・器具は存在しない
(サイトマップ・ショップページでも20商品)。

【価格・重量・在庫】
各商品のバリエーションのうち「豆のまま」×最小内容量(100g)のバリエーションを
Store API(`/products/<variation_id>`)で引き、その税込価格・在庫(is_in_stock)を採用する。
焙煎度は商品カテゴリ名(中煎り/中深煎り/深煎り)から取得する。ブレンドは商品名の「ブレンド」で判定。
産地は商品名(無ければ商品の短い説明文)から判定する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
)

SHOP_INFO = {
    "name": "かほり",
    "url": "https://www.kahori.biz/",
    "platform": "WooCommerce",
    "address": "福岡県那珂川市五郎丸2-42-1",
    "prefecture": "福岡県",
    "robots_txt_status": "確認済み(WooCommerce標準。商品ページ・Store APIは制限なし)",
}

BASE_URL = "https://www.kahori.biz"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_CATEGORIES = ("中深煎り", "中浅煎り", "浅煎り", "中煎り", "深煎り")
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップバッグ", "定期", "生豆")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)


def get_json(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_products() -> list[dict]:
    products = []
    for page in range(1, 10):
        batch = get_json(f"{BASE_URL}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        if not batch:
            break
        products += batch
        if len(batch) < 100:
            break
    return products


def pick_variation(product: dict) -> tuple[int, int] | None:
    """(重量g, バリエーションID)。豆のまま×最小重量を返す。"""
    best = None
    for v in product.get("variations", []):
        attrs = {a["name"]: a["value"] for a in v["attributes"]}
        wm = WEIGHT_PATTERN.search(attrs.get("内容量", ""))
        if not wm:
            continue
        w = int(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)
        grind = attrs.get("挽き方", "")
        rank = 0 if grind == "whole-bean" else 1
        key = (w, rank)
        if best is None or key < best[0]:
            best = (key, (w, v["id"]))
    return best[1] if best else None


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_all_products():
        title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", BeautifulSoup(p["name"], "html.parser").get_text())).strip()
        if any(k in title for k in EXCLUDE_KEYWORDS):
            continue
        if p.get("variations"):
            sel = pick_variation(p)
            if not sel:
                continue
            weight, vid = sel
            time.sleep(0.3)
            v = get_json(f"{BASE_URL}/wp-json/wc/store/v1/products/{vid}")
            price = int(v["prices"]["price"])
            in_stock = bool(v.get("is_in_stock"))
        else:
            wm = WEIGHT_PATTERN.search(title)
            if not wm:
                continue
            weight = int(wm.group(1))
            price = int(p["prices"]["price"])
            in_stock = bool(p.get("is_in_stock"))

        cats = [c["name"] for c in p.get("categories", [])]
        roast_level = next((c for c in cats if c in ROAST_CATEGORIES), None)
        short_text = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
        flavor_notes = re.sub(r"\s+", " ", short_text)[:400] or None

        parsed = parse_product(title)
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            # 「ハニーブレンド」等の商品名がハニープロセスと誤判定されるため、ブレンドは精製方法を持たせない
            parsed["processing_method"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(title)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"]:
                c = detect_country_name(short_text)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
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
            "roast_level": roast_level or parsed["roast_level"],
            "roast_hint": roast_level,
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": p["permalink"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kahori.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kahori.json に出力しました")


if __name__ == "__main__":
    main()
