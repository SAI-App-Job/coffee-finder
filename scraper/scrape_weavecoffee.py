# -*- coding: utf-8 -*-
"""
scrape_weavecoffee.py

Weave Coffee Roaster(weavecoffee.com、神奈川県茅ヶ崎市幸町21-32、JR茅ヶ崎駅から徒歩2分)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
神奈川県の新規発掘調査(2026-10-21)で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、バリエーションが
「<重量>g / <挽き方>」の組になっている焙煎豆(オリジン・ブレンド・デカフェ)を対象とする。
ドリップバッグ・水出しコーヒー・セミナーチケットは除外。インフューズド(果実発酵フレーバー)の
「コロンビア パパヨ ピーチ」と、その豆をブレンドに含む「オータム ブレンド」も除外した。
代表は最小重量(100g)の「豆のまま」バリエーション。焙煎度は説明文の【焙煎度合】から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Weave Coffee Roaster",
    "url": "https://weavecoffee.com/",
    "platform": "Shopify",
    "address": "神奈川県茅ヶ崎市幸町21-32",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(Shopify標準。/products.json は禁止されていない)",
    "source_note": "https://weavecoffee.com/products.json および https://weavecoffee.com/policies/legal-notice を2026-10-20に確認。商品は全件2026-10-21更新。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://weavecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"【焙煎度合\s*】\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_HANDLES = {
    "colombia-papayo-peach",  # インフューズド
    "autumn-blend-2026",      # インフューズド豆(パパヨ ピーチ)をブレンドに含む
}
EXCLUDE_TITLE_WORDS = ("ドリップバッグ", "水出し", "セミナー", "チケット")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if p["handle"] in EXCLUDE_HANDLES or any(w in title for w in EXCLUDE_TITLE_WORDS):
            continue
        if "インフューズド" in title or "INFUSED" in title.upper():
            continue

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and "豆のまま" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        roast_m = ROAST_PATTERN.search(body)
        roast = roast_m.group(1) if roast_m else None
        taste_m = re.search(r"【テイスト】\s*(.+?)\s*【", body)
        taste = taste_m.group(1).strip() if taste_m else None
        desc = body.replace("★オーナーコメント★", "").strip()[:400] or None

        # 商品名は和文名を採用(英語名の【】部分は残す)
        parsed = parse_product(title)
        if "ブレンド" in title or re.search(r"【コーヒー豆】\s*ブレンド", body):
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
        if "ナチュラル" in title and not parsed["processing_method"]:
            parsed["processing_method"] = "ナチュラル"
        if "ウォッシュド" in title and not parsed["processing_method"]:
            parsed["processing_method"] = "ウォッシュド"

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
            "flavor_notes": taste or desc,
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
    with open("data_weavecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_weavecoffee.json に出力しました")


if __name__ == "__main__":
    main()
