# -*- coding: utf-8 -*-
"""
scrape_coffeeroastsereno.py

Coffee Roast Sereno(sereno-etajima.com、広島県江田島市能美町鹿川2151-1。店舗情報ページの
記載で確認済み)の商品情報を取得する。Shopify(coffee-roast-sereno.myshopify.com)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、バリエーションに「200g」
等のg表記を持つ焙煎豆(シングルオリジン・ブレンド・デカフェ)を対象とする。product_typeは
空欄が多く判別に使えない。バリエーションが「10個」「20個」等の個数表記の商品は
1杯ドリップ(ドリップバッグ)のため除外する。最小重量のバリエーション(200g)の価格を代表とする。
商品名が産地を含まない銘柄(ドンキーベリー等)は、説明文から国名を検出できる場合のみ
産地を補完する(origin_source=description)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Coffee Roast Sereno",
    "url": "https://sereno-etajima.com/",
    "platform": "Shopify",
    "address": "広島県江田島市能美町鹿川2151-1",
    "prefecture": "広島県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://sereno-etajima.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_KEYWORDS = ["セット", "ギフト", "ドリップバッグ", "1杯ドリップ"]
# 店舗の「ブレンド豆」コレクションに属する商品(商品名に「ブレンド」を含まないものを含む)
BLEND_TITLES = {
    "完熟豆セレーノスペシャル",
    "江田島シティロースト（ヨーロピアンスペシャル）",
    "能美島ビターブレンド",
    "くじらブレンド",
    "ハワイアンプリンセス（ハワイコナブレンド）",
    "カリブの恋人（ブルーマウンテンブレンド）",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"[\s　]+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            # バリエーションが「10個」等の個数表記(1杯ドリップ)の商品は対象外
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if parsed["is_flavored"]:
            continue
        if title in BLEND_TITLES:
            parsed["category"] = "ブレンド"
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["origin_country"] and desc:
                detected = detect_country_name(desc)
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "description"

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
    with open("data_coffeeroastsereno.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeroastsereno.json に出力しました")


if __name__ == "__main__":
    main()
