# -*- coding: utf-8 -*-
"""
scrape_wakoya.py

和珈屋(shop.wakoya.com、福井県福井市福2丁目1914)の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「珈琲豆」の商品(シングル・ブレンド・デカフェ)を対象とする。「飲み比べセット」
(product_type「珈琲豆 飲み比べセット」)・ギフト・ドリップバッグ・リキッド・フィルター
類は除外。タイトルに「インフューズド」を含む商品(果実等を加える製法)も除外。
バリエーションは「100ℊ / 豆のまま」「300ｇ(お買い得) / 豆のまま」「100ℊ / 挽き」等で、
「豆のまま」の最小重量(100g)を代表とする。商品ページに焙煎度の記載はないため
焙煎度は取得しない(null)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "和珈屋",
    "url": "https://shop.wakoya.com/",
    "platform": "Shopify",
    "address": "福井県福井市福2丁目1914",
    "prefecture": "福井県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.wakoya.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "珈琲豆"
# 「ℊ」(U+210A)、全角「ｇ」、半角「g」の表記ゆれがある
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇℊ]")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = unicodedata.normalize("NFKC", p["title"])
        title = re.sub(r"[★☆]\s*NEW\s*[★☆]", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        if "インフューズド" in title or "セット" in title:
            continue

        weighted = []
        for v in p["variants"]:
            vt = unicodedata.normalize("NFKC", v.get("title") or "")
            if "豆のまま" not in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", body))
        body = re.sub(r"[★☆]\s*NEW\s*[★☆]", "", body).strip()
        desc = body[:400] if body and body != title else None

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

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
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
    with open("data_wakoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wakoya.json に出力しました")


if __name__ == "__main__":
    main()
