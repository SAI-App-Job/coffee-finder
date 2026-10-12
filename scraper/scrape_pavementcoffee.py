# -*- coding: utf-8 -*-
"""
scrape_pavementcoffee.py

PAVEMENT COFFEE ROASTERY(pavementroastery.jp、栃木県宇都宮市西3-1-2)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(栃木県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`全15商品のうち、ドリップバッグ2種
(handleが"drip-bag"で始まる)とインフューズド系のWater Melon(コロンビア Edwin Noreña)を除くコーヒー豆12銘柄(product_typeが空の商品が多いため
product_typeでは絞らない)。バリエーションは「150」「300」(g、単位表記なしの場合あり)で、
最小重量(150g)の価格・在庫を代表とする。「Momiji Blend」は単一バリエーション
(Default Title)で内容量の記載がないためweight_gはnull。焙煎度は本文の「Roast Level」から、
産地はタイトルの国名(検出できない場合は本文の「国」表記)から取る。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "PAVEMENT COFFEE ROASTERY",
    "url": "https://pavementroastery.jp/",
    "platform": "Shopify",
    "address": "栃木県宇都宮市西3-1-2",
    "prefecture": "栃木県",
    "robots_txt_status": "許可(Shopify標準構成。商品・コレクションのクロールを明示許可)",
}

BASE_URL = "https://pavementroastery.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"^\s*(\d+)\s*g?\s*$")
ROAST_PATTERN = re.compile(r"Roast\s*Level\s*[:：]\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")
COUNTRY_PATTERN = re.compile(r"(?:生産国|国)\s*[:：]?\s*([^\s,、/]+)")
# タイトルから産地を検出できない商品(ディカフェは本文にメキシコと明記)
ORIGIN_OVERRIDES = {"yruki-less-coffee": "メキシコ", "leste-timor-estado-village-timor-global": "東ティモール"}
# 新鮮なフルーツと一緒に発酵させてスイカの風味を付与するインフューズド系のため除外
EXCLUDED_HANDLES = {"colombia-edwin-norena-water-melon-carbonic-maceration"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p["handle"].startswith("drip-bag") or p["handle"] in EXCLUDED_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.match(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if weighted:
            weight, variant = min(weighted, key=lambda x: x[0])
            available = bool(variant.get("available"))
        else:
            weight, variant = None, p["variants"][0]
            available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None
        roast_m = ROAST_PATTERN.search(body)
        roast = roast_m.group(1) if roast_m else None

        parsed = parse_product(title)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
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
    with open("data_pavementcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pavementcoffee.json に出力しました")


if __name__ == "__main__":
    main()
