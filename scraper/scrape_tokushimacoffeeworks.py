# -*- coding: utf-8 -*-
"""
scrape_tokushimacoffeeworks.py

TOKUSHIMA COFFEE WORKS(徳島コーヒーワークス、有限会社オハラ、オンラインストア coffee-w.jp、
公式サイト coffee-w.com)の商品情報を取得する。Shopify。

【住所について】
実データ確認済み(2026-10-15): オンラインストアの特定商取引法表記(coffee-w.jp/pages/特定商取引法に基づく表記)の
所在地は「徳島県徳島市山城西1-7」(販売業者 有限会社オハラ、サービス名 TOKUSHIMA COFFEE WORKS)。
公式サイト会社概要でも本社・山城店が同住所。焙煎所はLabo珈琲研究所(徳島市大原町千代ヶ丸山30-8)。

【対象商品について】
実データ確認済み(2026-10-15): Shopifyの`/products.json`のうちproduct_typeが「コーヒー豆」の43商品
(シングルオリジン・ブレンド・デカフェ・オーガニック。うち3商品が完売)。
バリエーションは「<重量>g / <豆のまま|中挽>」で、豆のまま/中挽は同一商品なので、最小重量(100g、
秋ブレンド「しずむ太陽」は200gのみ、アイス用ブレンドは商品名の400gのみ)の価格を代表とする。
ドリップバッグ・ギフト・リキッド・お試しセット・手提げ袋・和三盆等は product_type が異なるため対象外。
価格は税込。

【robots.txtについて】
実データ確認済み(2026-10-15): Shopify標準で、User-agent: * は Allow: / 。商品JSONは許可範囲。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "TOKUSHIMA COFFEE WORKS",
    "url": "https://coffee-w.jp/",
    "platform": "Shopify",
    "address": "徳島県徳島市山城西1-7",
    "prefecture": "徳島県",
    "robots_txt_status": "許可(2026-10-15確認。Shopify標準で User-agent: * は Allow: /)",
}

BASE_URL = "https://coffee-w.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_TAGS = ("中浅煎り", "中深煎り", "浅煎り", "中煎り", "深煎り")
# 国名が商品名から検出できない銘柄(タグ・商品名の産地表記による)
ORIGIN_TAG_FALLBACK = ("東ティモール", "インドネシア", "コスタリカ", "コロンビア", "ブラジル", "エチオピア",
                       "グアテマラ", "タンザニア", "ニカラグア", "ペルー", "エクアドル", "パナマ")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        title = title.replace("インドネシア ・", "インドネシア・").replace("ブラジル ・", "ブラジル・")
        tags = p.get("tags") or []

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            # バリエーションに重量がない商品(アイス用ブレンド【400g】)は商品名の重量を採用
            m = WEIGHT_PATTERN.search(title)
            if not m:
                continue
            weighted = [(int(m.group(1)), v) for v in p["variants"]]
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        is_blend = "ブレンド" in title or "ブレンド" in tags
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if not detected:
                detected = next((t for t in tags if t in ORIGIN_TAG_FALLBACK), None)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if "カフェインレス" in tags or "デカフェ" in title:
                parsed["category"] = "デカフェ"

        roast = next((t for t in ROAST_TAGS if t in tags), None) or parsed["roast_level"]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
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
    with open("data_tokushimacoffeeworks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokushimacoffeeworks.json に出力しました")


if __name__ == "__main__":
    main()
