# -*- coding: utf-8 -*-
"""
scrape_amenokakucoffee.py

天迦久珈琲 -ROASTERY & BREAD-(amenokakucoffee.com、奈良県奈良市中新屋町18 ならまち本店、
ほか三条通り店 計3拠点)の焙煎豆を取得する。Shopify の /products.json を使用。

【対象】
コレクション「焙煎豆(roasted-beans)」「BLENDS」および焙煎済みのグアテマラ ゲイシャ
(ドリップ用の挽き指定があり、生豆ではないもの)。「※焙煎前の生豆です」と記載のある
【】付き商品(生豆)、ドリップバッグ、リキッド、器具、グッズ、パン等は除外。
11gの試飲サイズは避け、最小の実用重量(100g、ゲイシャのみ50g)を代表とする。
"""
import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "天迦久珈琲 -ROASTERY & BREAD-",
    "url": "https://amenokakucoffee.com/",
    "platform": "Shopify",
    "address": "奈良県奈良市中新屋町18",
    "prefecture": "奈良県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}
BASE_URL = "https://amenokakucoffee.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_RE = re.compile(r"(\d+)\s*(kg|g)", re.I)

# 焙煎済み豆の handle(URLデコード後)
TARGET_HANDLES = {
    "コロンビア-ウィラ-ジャワ-1",
    "エチオピア-ニグセ-ゲメダ-チレ-ウォッシュド-コピー",
    "インドネシア-マンデリン-ムンテ-ドライミル-ドロッサングール",
    "グアテマラ-アカテナンゴ-エルミラドール-ゲイシャのコピー",
    "天迦久-pacamara-blend-black-bitter",
    "天迦久-geisha-blend-white-well-balanced",
    "天迦久-geisha-blend-red-fruity",
}
BLEND_HANDLES = {"天迦久-pacamara-blend-black-bitter", "天迦久-geisha-blend-white-well-balanced",
                 "天迦久-geisha-blend-red-fruity"}


def weight_of(title):
    m = WEIGHT_RE.search(title or "")
    if not m:
        return None
    n = int(m.group(1))
    return n * 1000 if m.group(2).lower() == "kg" else n


def scrape_all_products():
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    records = []
    for p in resp.json()["products"]:
        handle = urllib.parse.unquote(p["handle"])
        if handle not in TARGET_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
        weighted = [(weight_of(v["title"]), v) for v in p["variants"]]
        weighted = [(w, v) for w, v in weighted if w]
        # 試飲サイズ(30g未満)は代表にしない
        cand = [(w, v) for w, v in weighted if w >= 30]
        if not cand:
            continue
        weight = min(w for w, v in cand)
        group = [v for w, v in cand if w == weight]
        variant = group[0]
        available = any(v.get("available") for v in group)
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if handle in BLEND_HANDLES or "BLEND" in title.upper():
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
            "product_url": f"{BASE_URL}/products/" + urllib.parse.quote(handle),
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_amenokakucoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amenokakucoffee.json に出力しました")


if __name__ == "__main__":
    main()
