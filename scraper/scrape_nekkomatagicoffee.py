# -*- coding: utf-8 -*-
"""
scrape_nekkomatagicoffee.py

根子マタギコーヒー(nekkomatagicoffee.com、秋田県北秋田市阿仁根子字根子又78、自家焙煎所)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(秋田県)の新規発掘で発見。トップページ・特定商取引法表記(/policies/legal-notice)
の所在地が一致することを確認(2026-10-13)。店舗は「焙煎所」(試飲して購入。カフェではない)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「焙煎豆」の
商品。タイトルに「サブスクリプション」「定期便」を含む定期便は除外。バリエーションは
「<重量>g / 豆のまま|挽いた豆」の組で、最小重量(100g)のバリエーションの価格を代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "根子マタギコーヒー",
    "url": "https://nekkomatagicoffee.com/",
    "platform": "Shopify",
    "address": "秋田県北秋田市阿仁根子字根子又78",
    "prefecture": "秋田県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://nekkomatagicoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "焙煎豆"
EXCLUDE_WORDS = ("サブスク", "定期便", "セット", "ドリップバッグ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
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

        roast_level = "浅煎り" if "浅煎り" in title else ("深煎り" if "深煎り" in title else None)

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
    with open("data_nekkomatagicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nekkomatagicoffee.json に出力しました")


if __name__ == "__main__":
    main()
