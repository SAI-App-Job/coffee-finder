# -*- coding: utf-8 -*-
"""
scrape_honokacoffee.py

HONOKA COFFEE(ほの香、https://ec.honokacoffee.com/、宮城県仙台市太白区富沢南1-4-10
本店)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(宮城県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうち、タイトルが「【コーヒー豆】」で
始まる焙煎豆(ブレンド3・シングルオリジン3の計6銘柄)を対象とする。
ドリップバッグ・コーヒーバッグ・スコーン・ギフト・セット・定期購入(500g)・
店舗利用チケット等は除外。バリエーションは「<重量>g / <挽き方>」の組で、
最小重量のバリエーション(150g or 200g)の価格を代表とする。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "HONOKA COFFEE",
    "url": "https://ec.honokacoffee.com/",
    "platform": "Shopify",
    "address": "宮城県仙台市太白区富沢南1-4-10",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://ec.honokacoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
TITLE_PREFIX = "【コーヒー豆】"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_KEYWORDS = ("ドリップバッグ", "コーヒーバッグ", "ギフト", "セット", "定期")
ROAST_PATTERN = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")


def coarse_roast(text: str | None) -> str | None:
    """「深煎」「中深煎」等の表記を「〜煎り」に統一して返す。"""
    if not text:
        return None
    m = ROAST_PATTERN.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    r = m.group(1)
    return r if r.endswith("り") else r + "り"


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
        if not title.startswith(TITLE_PREFIX):
            continue
        if any(k in title for k in EXCLUDE_KEYWORDS):
            continue
        name = title[len(TITLE_PREFIX):].strip()

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

        parsed = parse_product(name)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["grade"] = None
            parsed["designated_brand"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": coarse_roast(name) or parsed["roast_level"],
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
    with open("data_honokacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_honokacoffee.json に出力しました")


if __name__ == "__main__":
    main()
