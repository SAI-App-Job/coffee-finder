# -*- coding: utf-8 -*-
"""
scrape_baisenkoubousora.py

焙煎幸房“そら”(coffee-sora.shop、公式サイトcoffee-sora.com、岐阜県大垣市墨俣町二ツ木80-1、
注文後焙煎専門店)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「スペシャルティコーヒー」「デカフェ」の商品を対象とする(コピ・ルアク、ブルーマウンテン、
ゲイシャ等の高額品も豆なので含める)。除外: デカフェお試しセット(セット)、ギフトボックス、
ギフトセット、お試しセット、定期便、コーヒーの香り袋、マルコナ(ナッツ)、マグ、手提げ袋。
バリエーションは「<焙煎度> 豆のまま / <重量>g」「粉 / <重量>g」の組で、豆のまま
バリエーションのうち100g(なければ最小重量)の価格を代表とする(コピ・ルアクは
20g・50gの小分けがあるが100gを優先)。焙煎度は商品名末尾の【浅煎り】等、または
バリエーション名の「浅煎り」「中煎り」から取得する。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎幸房“そら”",
    "url": "https://coffee-sora.shop/",
    "platform": "Shopify",
    "address": "岐阜県大垣市墨俣町二ツ木80-1",
    "prefecture": "岐阜県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://coffee-sora.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = {"スペシャルティコーヒー", "デカフェ"}
EXCLUDE_KEYWORDS = ["セット", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
# coffee_parser.pyの辞書で産地を検出できない/誤検出しやすい商品名の明示(handle -> 産地)
ORIGIN_OVERRIDES = {
    "mandheling-aceh": "インドネシア",
    "yemen-mocha-bordeaux": "イエメン",
}


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def extract_flavor_notes(body: str) -> str | None:
    text = re.sub(r"\s+", " ", body)
    m = re.search(r"テイスティングノート(?:（[^）]*）)?\s*(.+?)(?:\s*[🎁🗓💡🫙🔁]|$)", text)
    if m:
        return m.group(1).strip()[:400]
    m = re.search(r"風味\s*(.+?)\s*苦味\s*[★☆]", text)
    if m:
        return m.group(1).strip()[:400]
    return text[:300] or None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") not in BEAN_TYPES:
            continue
        title = clean_title(p["title"])
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "粉" in vt.split("/")[0] and "豆のまま" not in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        candidates = [x for x in weighted if x[0] >= 100] or weighted
        weight = min(w for w, _ in candidates)
        variants_at = [v for w, v in weighted if w == weight]
        variant = variants_at[0]
        available = any(v.get("available") for v in variants_at)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        flavor_notes = extract_flavor_notes(body)

        roast_m = ROAST_PATTERN.search(title) or ROAST_PATTERN.search(variant.get("title") or "")
        roast_level = roast_m.group(1) if roast_m else None
        name = re.sub(r"【(?:中浅煎り|中深煎り|浅煎り|中煎り|深煎り)】", "", title).strip()

        parsed = parse_product(name)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{urllib.parse.quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_baisenkoubousora.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisenkoubousora.json に出力しました")


if __name__ == "__main__":
    main()
