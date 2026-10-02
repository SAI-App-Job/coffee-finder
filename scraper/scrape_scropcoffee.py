# -*- coding: utf-8 -*-
"""
scrape_scropcoffee.py

Scrop COFFEE ROASTERS(scrop-coffee-roasters.com、千葉県流山市おおたかの森南1-5-1
流山おおたかの森S・C 3F が常設店舗、焙煎は埼玉県熊谷市の自社焙煎工場)の商品情報を
取得する。Shopify。

【店舗発見の経緯】
埼玉県再調査の新規発掘で発見したが、常設店舗が千葉県流山市のため千葉県の調査へ
引き継いだ。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「コーヒー豆」の商品(オリジン・ブレンド・デカフェ)を対象とする。タイトルに「セット」を
含むテイスティングセット等は除外。バリエーションは「<重量>g / <挽き方>」の組で、
最小重量のバリエーション(多くは100g、ゲイシャ等の希少ロットは50g)の価格を代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Scrop COFFEE ROASTERS",
    "url": "https://scrop-coffee-roasters.com/",
    "platform": "Shopify",
    "address": "千葉県流山市おおたかの森南1-5-1 流山おおたかの森S・C 3F",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://scrop-coffee-roasters.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        title = re.sub(r"^【SOLD OUT】\s*", "", title)
        if "セット" in title:
            continue

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
        desc = re.sub(r"\s+", " ", body)[:400] or None

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
    with open("data_scropcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_scropcoffee.json に出力しました")


if __name__ == "__main__":
    main()
