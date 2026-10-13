# -*- coding: utf-8 -*-
"""
scrape_sarugasancoffee.py

猿賀山珈琲焙煎所(喫茶室baton直営、https://craftcoffeeroastery.com/、青森県平川市猿賀石林58-11)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(青森県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`の45商品(product_typeは全て
「食品・飲料」)はすべて150gの自家焙煎コーヒー豆(シングルオリジン・ブレンド・デカフェ)で、
ドリップバッグ・ギフト・雑貨は含まれない。バリエーションは150gのみ。
産地・精製方法・焙煎度は商品説明本文の表(原産国 / 精製方法 / 焙煎度)から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "猿賀山珈琲焙煎所",
    "url": "https://craftcoffeeroastery.com/",
    "platform": "Shopify",
    "address": "青森県平川市猿賀石林58-11",
    "prefecture": "青森県",
    "robots_txt_status": "許可(User-agent: *でAllow: /。Shopify標準構成)",
}

BASE_URL = "https://craftcoffeeroastery.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ORIGIN_PATTERN = re.compile(r"原産国 / origin\s*(.*?)\s*品種")
PROCESS_PATTERN = re.compile(r"精製方法 / proccess\s*(.*?)\s*焙煎度")
ROAST_PATTERN = re.compile(r"焙煎度 / roasted\s*(.*?)\s*CUPPING")
CUPPING_PATTERN = re.compile(r"CUPPING NOTE\s*(.*?)\s*(?:\(Acidity\)|酸味 \(Acidity\))")

# 説明表の原産国表記(「中国・雲南省」等)を国名に正規化する
COUNTRY_NORMALIZE = {"中国・雲南省": "中国"}


def normalize_roast(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.replace("シティーロースト", "シティロースト")
    for kw in ["ライトロースト", "ミディアムロースト", "シティロースト", "ダークロースト"]:
        if kw in raw:
            return kw
    return raw


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k in title for k in ["ドリップバッグ", "セット", "ギフト", "詰め合わせ"]):
            continue

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
        body = re.sub(r"\s+", " ", body)
        cupping = CUPPING_PATTERN.search(body)
        desc = (cupping.group(1) if cupping else body)[:400] or None
        origin_m = ORIGIN_PATTERN.search(body)
        process_m = PROCESS_PATTERN.search(body)
        roast_m = ROAST_PATTERN.search(body)

        parsed = parse_product(title)
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
            if not parsed["origin_country"] and origin_m:
                parsed["origin_country"] = COUNTRY_NORMALIZE.get(origin_m.group(1), origin_m.group(1))
                parsed["origin_source"] = "description"
            if not parsed["processing_method"] and process_m:
                pm = parse_product(process_m.group(1))["processing_method"]
                parsed["processing_method"] = pm
        roast = normalize_roast(roast_m.group(1)) if roast_m else None

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
    with open("data_sarugasancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sarugasancoffee.json に出力しました")


if __name__ == "__main__":
    main()
