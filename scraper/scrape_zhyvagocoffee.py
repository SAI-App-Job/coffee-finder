# -*- coding: utf-8 -*-
"""
scrape_zhyvagocoffee.py

ZHYVAGO COFFEE ROASTERY(shop.zhyvagocoffeeroastery.coffee、沖縄県中頭郡北谷町美浜34-1
LeQu沖縄北谷スパ&リゾート プレミア棟1F)の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「コーヒー豆」の
商品を対象とする。バリエーションは「<重量>g / <挽き方> / <配送>」の組で、最小重量(100g)の
バリエーションの価格を代表とする。
- 「SINGLE ORIGIN VIETNAM」(Zanya / ラベンダー共発酵)はラベンダーを発酵工程に加える
  インフューズド系のため除外。
- TRIP PACK(ドリップ)・ギフト・グッズ・菓子類(product_typeが別)は対象外。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ZHYVAGO COFFEE ROASTERY",
    "url": "https://shop.zhyvagocoffeeroastery.coffee/",
    "platform": "Shopify",
    "address": "沖縄県中頭郡北谷町美浜34-1 LeQu沖縄北谷スパ&リゾート プレミア棟1F",
    "prefecture": "沖縄県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.zhyvagocoffeeroastery.coffee"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
# インフューズド系(花・果実・ハーブ等を加える共発酵)は除外
EXCLUDE_HANDLES = {"beans-single-origin-vietnam"}
# 商品名が国名のみのため、商品説明冒頭の農園・精製を補う
NAME_OVERRIDES = {
    "beans-single-origin-costa-rica": "SINGLE ORIGIN COSTA RICA La Candelilla (Honey)",
}
# 商品名が国名のみのため、商品説明冒頭の農園・精製を補う
NAME_OVERRIDES = {
    "beans-single-origin-costa-rica": "SINGLE ORIGIN COSTA RICA La Candelilla (Honey)",
}
EXCLUDE_WORDS = ("共発酵", "co-ferment", "インフューズ", "Infused")


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^\[BEANS\]\s*", "", title)
    return title


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        if p["handle"] in EXCLUDE_HANDLES:
            continue
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        if any(w.lower() in (p["title"] + body).lower() for w in EXCLUDE_WORDS):
            continue
        title = clean_title(p["title"])

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, _ in weighted)
        # 最小重量のうち最初のバリエーション(挽き方・配送違いは同価格)
        cand = [v for w, v in weighted if w == weight]
        variant = cand[0]
        available = any(v.get("available") for v in cand)

        # 商品説明(産地・農園・味わい)を整形
        desc = body[:400] or None

        # 商品名は「SINGLE ORIGIN COSTA RICA」等で、説明冒頭の銘柄(農園名・精製)を補う
        raw_name = NAME_OVERRIDES.get(p["handle"], title)
        parsed = parse_product(raw_name)
        if "ブレンド" in raw_name or "BLEND" in raw_name.upper():
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(body) or detect_country_name(raw_name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, raw_name)

        roast_level = parsed["roast_level"]
        if not roast_level:
            rm = re.search(r"Roast Level\(焙煎度合\)：\s*([A-Za-z ]+?roast)", body, re.I)
            if rm:
                roast_level = {"light": "浅煎り", "medium": "中煎り", "dark": "深煎り"}.get(rm.group(1).split()[0].lower(), rm.group(1).strip())
        if "ブレンド" == parsed["category"] and not roast_level and "深煎り" in body:
            roast_level = "深煎り"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
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
    with open("data_zhyvagocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_zhyvagocoffee.json に出力しました")


if __name__ == "__main__":
    main()
