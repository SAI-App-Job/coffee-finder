# -*- coding: utf-8 -*-
"""
scrape_miraiseeds.py

Mirai Seeds (Roastery & Laboratory)(miraiseeds.net、三重県津市芸濃町椋本5478、
株式会社MIRAI SEEDS)の商品情報を取得する。Shopify。ブラジル・ミナスジェライス州の
グアリロバ農園(COE 2016 第1位)の豆だけを使った自家焙煎。

【店舗発見の経緯】
全国再調査(三重県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`の10商品のうち、
「お試し3種セット 100g×3」(セット)を除く9商品(ブレンド8・シングル1)を対象とする。
バリエーションは「<重量> / <挽き方>」の組(100g・500g・2kg・一部5kg)で、
最小重量(100g)のバリエーションの価格を代表とする。
商品名は「<銘柄> ー <キャッチコピー>」形式なので「ー」より前を銘柄名とし、
「フルーティー」のみ本文タイトルの「グアリロバ・フルーティー」を銘柄名とする。
焙煎度は本文の「商品情報 焙煎度」欄から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Mirai Seeds (Roastery & Laboratory)",
    "url": "https://www.miraiseeds.net/",
    "platform": "Shopify",
    "address": "三重県津市芸濃町椋本5478",
    "prefecture": "三重県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://www.miraiseeds.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
ROAST_PATTERN = re.compile(r"商品情報 焙煎度 (.+?) 浅煎り 中煎り 中深煎り 深煎り")

# 銘柄名の上書き(タイトルが「フルーティー ー ...」のみで銘柄が分からないため)
NAME_OVERRIDES = {"guariroba-fruity-tropical-sweet-vibrant": "グアリロバ・フルーティー"}
# ブレンドでない(農園のロットそのもの)商品: 産地を明示する
SINGLE_ORIGIN = {"guariroba-fruity-tropical-sweet-vibrant": "ブラジル"}


def to_grams(v: str) -> int | None:
    m = WEIGHT_PATTERN.search(v or "")
    if not m:
        return None
    n = int(m.group(1))
    return n * 1000 if m.group(2).lower() == "kg" else n


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title:
            continue
        name = NAME_OVERRIDES.get(p["handle"]) or re.split(r"\s+ー\s+", title)[0].strip()

        weighted = []
        for v in p["variants"]:
            g = to_grams(v.get("title"))
            if g:
                weighted.append((g, v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        roast_m = ROAST_PATTERN.search(body)
        roast = roast_m.group(1) if roast_m else None
        desc = body[:400] or None

        parsed = parse_product(name)
        if p["handle"] in SINGLE_ORIGIN:
            parsed["category"] = "ストレート"
            parsed["origin_country"] = SINGLE_ORIGIN[p["handle"]]
            parsed["origin_source"] = "description"
        elif "ブレンド" in name or "カクテル" in name or "トパーズ" in name or "アイシー" in name:
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
    with open("data_miraiseeds.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_miraiseeds.json に出力しました")


if __name__ == "__main__":
    main()
