# -*- coding: utf-8 -*-
"""
scrape_glincoffee.py

glin coffee(glincoffee.jp、川越市脇田本町8-1 U_PLACE 1Fの「glin coffee ROASTERY
U_PLACE店」。川越市内に元町一号店・時の鐘店・U_PLACE店・伊佐沼グリーンツーリズム店の
4店舗を展開し、11店舗未満)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`(plain requestsで取得可)
のうち、product_typeが「コーヒー豆」の9件から、飲み比べセット(50g×3)を除いた
8銘柄(ブレンド4・ストレート4、デカフェ1含む)を対象とする。内容量は商品説明の
「内容量：100g」に明記されている(variantのgramsは梱包重量のため使わない)。
商品名先頭の【中浅煎り】等は焙煎度としてroast_levelに移し、名称から除去する
(「中煎深り」は説明文の「ロースト：中深煎り」から中深煎りの誤記と判断)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "glin coffee",
    "url": "https://glincoffee.jp/",
    "platform": "Shopify",
    "address": "埼玉県川越市脇田本町8-1 U_PLACE 1F",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://glincoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ROAST_PREFIX = re.compile(r"^【(中煎深り|中深煎り|中浅煎り|中煎り|浅煎り|深煎り)】\s*")
WEIGHT_PATTERN = re.compile(r"内容量[:：]\s*(\d+)\s*[gｇ]")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != "コーヒー豆":
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title:
            continue

        roast_m = ROAST_PREFIX.match(title)
        roast_level = None
        if roast_m:
            roast_level = "中深煎り" if roast_m.group(1) == "中煎深り" else roast_m.group(1)
        name = ROAST_PREFIX.sub("", title)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        weight_m = WEIGHT_PATTERN.search(body)
        desc = re.sub(r"\s+", " ", body)[:400] or None
        variant = p["variants"][0]
        available = any(v.get("available") for v in p["variants"])

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
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
            "roast_level": roast_level or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": int(weight_m.group(1)) if weight_m else None,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_glincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_glincoffee.json に出力しました")


if __name__ == "__main__":
    main()
