# -*- coding: utf-8 -*-
"""
scrape_gluckcoffeespot.py

Gluck Coffee Spot(gluckcoffeespot.jp、熊本県熊本市中央区城東町5-52)の商品情報を取得する。
Shopify。「熊本の自家焙煎スペシャルティコーヒー専門店」(公式サイトのtitle)。

【店舗発見の経緯】
全国再調査(熊本県)で発見。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(15件)のうち、バリエーションが
「<重量>g / 豆のまま」「<重量>g / 細挽き…」の形式のコーヒー豆7種(シングルオリジン6、
中煎りエスプレッソ用1を含む)。ギフトボックス・コーヒーバッグ・手ぬぐい・おまかせセット
(重量表記なし)は除外。定期便専用の gluckcoffee.base.shop は対象外。
代表は「豆のまま」バリエーションのうち最小重量(通常200g、【SPECIAL】のみ100g)。
焙煎度は説明文の「焙煎度:」、または商品名の【MEDIUM ROAST】【DARK ROAST】から取る。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import detect_processing_method, parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Gluck Coffee Spot",
    "url": "https://gluckcoffeespot.jp/",
    "platform": "Shopify",
    "address": "熊本県熊本市中央区城東町5-52",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://gluckcoffeespot.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
VARIANT_PATTERN = re.compile(r"^(\d+)\s*g\s*/\s*豆のまま")
EXCLUDE_WORDS = ("ギフト", "セット", "Coffee Bag")
ROAST_BODY_PATTERN = re.compile(r"焙煎度\s*[:：]\s*(中深煎り|中浅煎り|深煎り|中煎り|浅煎り)")
TITLE_ROAST = {"MEDIUM ROAST": "中煎り", "DARK ROAST": "深煎り"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
            continue
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
        if parsed["category"] != "ブレンド":
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
        else:
            parsed["origin_country"] = None
            parsed["origin_source"] = None

        pm = re.search(r"精\s*製\s*[:：]\s*(\S+)", body)
        if pm and not parsed["processing_method"]:
            parsed["processing_method"] = detect_processing_method(pm.group(1))
        roast_level = parsed["roast_level"]
        m = ROAST_BODY_PATTERN.search(body)
        if m:
            roast_level = m.group(1)
        else:
            for key, val in TITLE_ROAST.items():
                if key in title:
                    roast_level = val
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
    with open("data_gluckcoffeespot.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gluckcoffeespot.json に出力しました")


if __name__ == "__main__":
    main()
