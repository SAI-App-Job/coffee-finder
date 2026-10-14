# -*- coding: utf-8 -*-
"""
scrape_thothcoffee.py

トートコーヒー(THOTH COFFEE、thothcoffee.com、香川県綾歌郡宇多津町)の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10-15): `/products.json`のうちproduct_typeが「コーヒー豆」で始まる商品
(「コーヒー豆　シングル」「コーヒー豆　ブレンド」)がコーヒー豆本体。デカフェ2銘柄はシングルに
含まれる。ギフト・ドリップバッグ・水出しパック・アイスコーヒー(ボトル)・器具は除外。
バリエーションは「<重量>g / <挽き方>」で、最小重量(多くは100g、ペルーCOEゲイシャのみ50g)を代表とする。
「オータム2026」は product_type が「シングル」だが説明文が秋限定ブレンドなのでブレンド扱いとする。
(handleは過去商品のまま流用されており、商品名と一致しない。URLはhandleで一意)
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "トートコーヒー",
    "url": "https://thothcoffee.com/",
    "platform": "Shopify",
    "address": "香川県綾歌郡宇多津町浜一番丁3-8",
    "prefecture": "香川県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://thothcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
FORCE_BLEND_TITLES = {"オータム2026"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        ptype = p.get("product_type") or ""
        if not ptype.startswith("コーヒー豆"):
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None

        parsed = parse_product(title)
        if "ブレンド" in ptype or title in FORCE_BLEND_TITLES:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        rm = ROAST_PATTERN.search(title) or ROAST_PATTERN.search(body)
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
            "roast_hint": rm.group(1) if rm else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_thothcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_thothcoffee.json に出力しました")


if __name__ == "__main__":
    main()
