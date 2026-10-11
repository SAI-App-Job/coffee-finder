# -*- coding: utf-8 -*-
"""
scrape_comeyasucoffee.py

米安珈琲(comeyasu-store.com、滋賀県守山市守山1-11-12)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(滋賀県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、コーヒー豆の単品
(シングルオリジン・ブレンド)を対象とする。ドリップパック、ギフトBOX、「N本セット」は除外。
バリエーションは「<挽き方> / <重量>g」(100g/200g/300g)で、最小重量(100g)の価格を代表とする。
焙煎度は商品名・本文に表記がないため、店の焙煎度別コレクション
(浅・中煎り=chuuiri、中深煎り=chuubukairi、深煎り=hukairi)の所属から付与する。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "米安珈琲",
    "url": "https://comeyasu-store.com/",
    "platform": "Shopify",
    "address": "滋賀県守山市守山1-11-12",
    "prefecture": "滋賀県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://comeyasu-store.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_KEYWORDS = ["ドリップパック", "ギフト", "セット", "本セット"]
# coffee_parser.pyの国名辞書で検出できない表記(「インディア」「ニューギニア」)の産地を明示する
ORIGIN_OVERRIDES = {"india": "インド", "newguinea": "パプアニューギニア"}
ROAST_COLLECTIONS = {
    "chuuiri": "浅煎り〜中煎り",
    "chuubukairi": "中深煎り",
    "hukairi": "深煎り",
}


def fetch_roast_map() -> dict[str, str]:
    roast_map = {}
    for coll, roast in ROAST_COLLECTIONS.items():
        resp = requests.get(f"{BASE_URL}/collections/{coll}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        for p in resp.json().get("products", []):
            roast_map[p["handle"]] = roast
    return roast_map


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])
    roast_map = fetch_roast_map()

    records = []
    for p in products:
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
        weight = min(w for w, v in weighted)
        rep = [v for w, v in weighted if w == weight]
        variant = rep[0]
        available = any(v.get("available") for v in rep)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parse_name = unicodedata.normalize("NFKC", title)
        parsed = parse_product(parse_name)
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(parse_name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, parse_name)
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
            "roast_level": roast_map.get(p["handle"]) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_comeyasucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_comeyasucoffee.json に出力しました")


if __name__ == "__main__":
    main()
