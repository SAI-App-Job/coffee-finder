# -*- coding: utf-8 -*-
"""
scrape_mamekichian.py

豆吉庵(mamekichi-an.com、静岡県磐田市国府台86-1-105)の商品情報を取得する。
WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products?per_page=100)。

【商品構造について】
実データ確認済み(2026-10-06時点、全13件): カテゴリ「珈琲豆」の商品のうち、
「お試しセット」(50g x 4袋のセット)と「クール便」(送料オプション)は除外し、
ペーパー&器具も除外する。残りの豆8点(シングル5・ブレンド3)が対象。
商品名末尾の「200g＊」から重量を読み取る。ケニア ギチャサイニは
内容量バリエーション(150g=1,875円 / 200g=2,500円)があるため、最小重量の150gを代表とする。
roast はdescription内の「中深炒り」「深炒り」表記から取得する(無い商品は None)。
"""

import html
import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "豆吉庵",
    "url": "https://www.mamekichi-an.com/",
    "platform": "WordPress + WooCommerce",
    "address": "静岡県磐田市国府台86-1-105",
    "prefecture": "静岡県",
    "robots_txt_status": "未確認",
}

API_URL = "https://www.mamekichi-an.com/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORY = "珈琲豆"
EXCLUDE_KEYWORDS = ["セット", "クール便", "ペーパー", "ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(中深|中浅|浅|中|深)炒り")
ROAST_MAP = {"中深": "中深煎り", "中浅": "中浅煎り", "浅": "浅煎り", "中": "中煎り", "深": "深煎り"}


def fetch_products() -> list[dict]:
    products, page = [], 1
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
    return products


def clean_name(raw: str) -> str:
    name = unicodedata.normalize("NFKC", html.unescape(raw))
    name = name.replace("＊", "").replace("*", "")
    name = re.sub(r"\s*\d+\s*g\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        cats = [html.unescape(c["name"]) for c in p["categories"]]
        raw = html.unescape(p["name"])
        norm = unicodedata.normalize("NFKC", raw)
        if BEAN_CATEGORY not in cats or any(k in norm for k in EXCLUDE_KEYWORDS):
            continue
        name = clean_name(raw)

        # 重量: バリエーション(内容量)があれば最小、無ければ名称末尾の重量
        weight = None
        price = int(p["prices"]["price"]) if p["prices"].get("price") else None
        for a in p["attributes"]:
            if a["name"] == "内容量":
                ws = []
                for t in a["terms"]:
                    m = WEIGHT_PATTERN.search(t["name"])
                    if m:
                        ws.append(int(m.group(1)))
                if ws:
                    weight = min(ws)
        if weight is None:
            m = WEIGHT_PATTERN.search(norm)
            weight = int(m.group(1)) if m else None
        # price_range.min は最小重量バリエーションの価格
        pr = p["prices"].get("price_range")
        if pr and pr.get("min_amount"):
            price = int(pr["min_amount"])

        short = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
        long_ = BeautifulSoup(p.get("description") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", (short + " " + long_).strip())
        flavor_notes = desc[:400] or None
        rm = ROAST_PATTERN.search(desc)
        roast = ROAST_MAP[rm.group(1)] if rm else None

        is_blend = "ブレンド" in name or "ブレンド" in cats
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)

        in_stock = bool(p["is_in_stock"])
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
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
    with open("data_mamekichian.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekichian.json に出力しました")


if __name__ == "__main__":
    main()
