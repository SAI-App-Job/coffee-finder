# -*- coding: utf-8 -*-
"""
scrape_junctioncoffee.py

JUNCTION Coffee Roaster(junction-coffee.com、熊本県熊本市東区錦ケ丘26-17)の商品情報を
取得する。Shopify。公式サイトのmeta説明に「豆の買い付けから焙煎も自社で行なっており」と明記。

【店舗発見の経緯】
全国再調査(熊本県)で発見。

【住所について(要確認)】
特定商取引法の表記は「〒861-4616 熊本県上益城郡甲佐町田口1247-1」(オーナー出身地の甲佐町)。
一方、公式のACCESSページに貼られたGoogleマップの店舗ピン(JUNCTION Coffee Roaster (COFFEE STAND))は
熊本市東区錦ケ丘付近を指し、もう1つの焙煎場ピンは熊本市中央区大江付近を指す。公式メタ説明も
「熊本市東区にある」とし、ウォーカープラス記事(2022年)も店舗を「熊本県熊本市東区錦ケ丘26-17
さくら荘101」と報じている。特商法の甲佐町は店舗・焙煎場の所在地と一致しないため、
地図表示用には店舗の熊本市東区の住所を採用した(特商法の甲佐町は事業者所在地の可能性)。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(7件)のうちproduct_typeが「コーヒー豆」で
「セット」を含まない5種(ゲイシャ2種=100g、150g、200g)。WEB限定3種セットとTシャツは除外。
バリエーションは1つ(Default Title)で、重量は商品名の「100g」等から取る。
焙煎度は商品名の【浅煎り】【深煎り】から取る。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "JUNCTION Coffee Roaster",
    "url": "https://junction-coffee.com/",
    "platform": "Shopify",
    "address": "熊本県熊本市東区錦ケ丘26-17",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://junction-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
ROAST_PATTERN = re.compile(r"【(中深煎り|中浅煎り|深煎り|中煎り|浅煎り)")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title:
            continue
        m = WEIGHT_PATTERN.search(title)
        if not m:
            continue
        weight = int(m.group(1))
        variant = p["variants"][0]
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
        rm = ROAST_PATTERN.search(title)
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
    with open("data_junctioncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_junctioncoffee.json に出力しました")


if __name__ == "__main__":
    main()
