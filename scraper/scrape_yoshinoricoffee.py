# -*- coding: utf-8 -*-
"""
scrape_yoshinoricoffee.py

yoshinori coffee(ヨシノリコーヒー、yoshinoricoffee-online.com、公式サイト
https://www.yoshinoricoffee.com/、北海道上川郡東川町北町12丁目11番1号)の商品情報を
取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`全18商品のうち、
自家焙煎豆(シングルオリジン7・ブレンド5)を対象とする。ギフトBOX・コーヒーバッグ・
コーヒーベース・ポスト便・紅白蝶結び(のし)は除外。
バリエーションは「<豆/挽き方> / <重量>」(順序は商品により逆)の組で、挽き方は
「豆」のバリエーションに限定し、最小重量(100g)の価格・在庫を代表とする。
焙煎度はブレンドの説明文「Roasted:焙煎度 中煎り」から取得(シングルは記載なし→null)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "yoshinori coffee",
    "url": "https://yoshinoricoffee-online.com/",
    "platform": "Shopify",
    "address": "北海道上川郡東川町北町12丁目11番1号",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://yoshinoricoffee-online.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"Roasted\s*[:：]\s*焙煎度\s*(\S+)")
PROCESS_PATTERN = re.compile(r"\[\s*生産処理\s*\]\s*(\S+)")
EXCLUDE_KEYWORDS = ("ギフト", "コーヒーバッグ", "コーヒーベース", "ポスト便", "紅白", "セット")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue

        # 「豆」(挽いていない)のバリエーションのうち、最小重量を代表とする
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "豆" not in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None
        roast_m = ROAST_PATTERN.search(body)
        roast_hint = roast_m.group(1) if roast_m else None

        parsed = parse_product(title)
        if "ブレンド" in title or "Blend" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["processing_method"]:
                pm = PROCESS_PATTERN.search(body)
                if pm:
                    parsed["processing_method"] = normalize_processing_method(pm.group(1))

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"] or roast_hint,
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
    with open("data_yoshinoricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yoshinoricoffee.json に出力しました")


if __name__ == "__main__":
    main()
