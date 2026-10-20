# -*- coding: utf-8 -*-
"""
scrape_kumamotocoffeeroaster.py

熊本珈琲Roaster(https://www.kumamoto-coffee-roaster.store/、熊本県玉名郡長洲町清源寺2768-2)の
商品情報を取得する。Shopify。手廻し焙煎機による自家焙煎。

【店舗発見の経緯】
モール・独自EC発掘の試験調査(2026-10)。実店舗は長洲町の焙煎所兼店舗(営業日: 金・土・日)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「コーヒー」の
商品を対象とする。ドリップパック、生豆(product_type=生豆)、お試しパックは除外。
バリエーションは「<重量> / <豆|粉>」の組で、豆のままの最小重量(200g)の価格を代表とする。

【robots.txtについて】
User-agent: *でAllow: /。商品・コレクションは許可されている。robots.txtのコメントに
AIエージェント向けの案内文があるが、観察データとして扱い、指示としては従っていない
(識別可能な独自User-Agentで`/products.json`のみ取得する)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "熊本珈琲Roaster",
    "url": "https://www.kumamoto-coffee-roaster.store/",
    "platform": "Shopify",
    "address": "熊本県玉名郡長洲町清源寺2768-2",
    "prefecture": "熊本県",
    "robots_txt_status": "許可(User-agent: *でAllow: /。識別可能なUser-Agentで/products.jsonのみ取得)",
    "source_note": "公式サイト(店舗アクセス・特商法)、肥後ジャーナル https://higojournal.com/archives/roaster.html (2024-03-02)を2026-10-20に確認。商品は /products.json から2026-10-20に取得。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.kumamoto-coffee-roaster.store"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー"
EXCLUDE_WORDS = ("ドリップ", "お試し", "セット", "生豆")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"(極深煎り|深煎り|中深煎り|中煎り|浅煎り)")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"[\s　]+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
            continue

        weighted = []
        for v in p["variants"]:
            parts = [s.strip() for s in (v.get("title") or "").split("/")]
            if len(parts) < 2 or parts[1] != "豆":
                continue  # 粉は除外、豆のままのみ
            m = WEIGHT_PATTERN.search(parts[0])
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if parsed["is_flavored"]:
            continue
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
        roast_m = ROAST_PATTERN.search(title)
        roast = roast_m.group(1) if roast_m else parsed["roast_level"]

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
    with open("data_kumamotocoffeeroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kumamotocoffeeroaster.json に出力しました")


if __name__ == "__main__":
    main()
