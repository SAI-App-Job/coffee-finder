# -*- coding: utf-8 -*-
"""
scrape_bagtowncoffee.py

BAGTOWN COFFEE(bagtowncoffee.com、広島県広島市中区袋町2-1)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「beans」の
商品(シングルオリジン・ブレンド・デカフェ)を対象とする。定期便(気まぐれ五彩ロースト)、
ドリップバッグ詰め合わせ、コーヒーギフトセット(product_typeがbeansでも別商品)、
[INFUSED](ブラックベリー共発酵のインフューズド)は除外。
バリエーションは「<重量>g / <挽き方>」の組で、最小重量のバリエーション(多くは200g、
一部は100g、希少ロットは20g)の価格を代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BAGTOWN COFFEE",
    "url": "https://bagtowncoffee.com/",
    "platform": "Shopify",
    "address": "広島県広島市中区袋町2-1",
    "prefecture": "広島県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://bagtowncoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "beans"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_KEYWORDS = ["定期便", "セット", "SET", "ギフト", "ドリップバッグ", "フリーズドライ", "INFUSED"]
ROAST_TAGS = {"極深煎り": "極深煎り", "深煎り": "深煎り", "中深煎り": "中深煎り", "中煎り": "中煎り", "浅煎り": "浅煎り"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
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
        if parsed["is_flavored"]:
            continue
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        roast = parsed["roast_level"]
        if not roast:
            tags = p.get("tags") or []
            for key in ("極深煎り", "中深煎り", "深煎り", "中煎り", "浅煎り"):
                if key in tags:
                    roast = ROAST_TAGS[key]
                    break

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
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
    with open("data_bagtowncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bagtowncoffee.json に出力しました")


if __name__ == "__main__":
    main()
