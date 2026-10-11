# -*- coding: utf-8 -*-
"""
scrape_cafebanana.py

CAFE BANANA FRUITS & COFFEE ROASTERS(cafebanana.jp、熊本県山鹿市山鹿1849)の商品情報を
取得する。Shopify。公式のmeta説明に「世界各国のスペシャルティ珈琲を日々焙煎してお客様に
お届けします」とある(山鹿温泉街・豊前街道のスペシャルティ珈琲と果物の専門店)。

【店舗発見の経緯】
全国再調査(熊本県)で発見。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(12件)のうちproduct_typeが「coffee」の
コーヒー豆4種(シングルオリジン)。果物(栗・西瓜・メロン等)、トートバッグ・エコバッグ・
Tシャツ、STEN FLAMEは除外。バリエーションは「100g/250g/500g」×「豆のまま/粉」で、
「豆のまま」の最小重量(100g、各800円)を代表とする。焙煎度は説明文の「(中煎り)」から取る。
商品名が英語表記のため、産地は商品名の国名から取る。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "CAFE BANANA FRUITS & COFFEE ROASTERS",
    "url": "https://cafebanana.jp/",
    "platform": "Shopify",
    "address": "熊本県山鹿市山鹿1849",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://cafebanana.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "coffee"
VARIANT_PATTERN = re.compile(r"^(\d+)\s*g\s*/\s*豆のまま")
ROAST_PATTERN = re.compile(r"[（(](中深煎り|中浅煎り|深煎り|中煎り|浅煎り)[）)]")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        weighted = []
        for v in p["variants"]:
            m = VARIANT_PATTERN.match((v.get("title") or "").strip())
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = re.sub(r"\s+", " ", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        desc = body[:400] or None

        parsed = parse_product(title)
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

        roast_level = parsed["roast_level"]
        rm = ROAST_PATTERN.search(body)
        if rm:
            roast_level = rm.group(1)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
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
    with open("data_cafebanana.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafebanana.json に出力しました")


if __name__ == "__main__":
    main()
