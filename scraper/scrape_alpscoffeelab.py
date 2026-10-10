# -*- coding: utf-8 -*-
"""
scrape_alpscoffeelab.py

Alps coffee lAb.(https://alps-coffee-lab.com、長野県松本市中央2-4-9)の商品情報を取得する。
Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「コーヒー豆」の
商品が22件あるが、うち17件は果実・酒類・香辛料・燻製等を加えたインフューズド(フレーバー)
コーヒー(オレンジ/バナナ/レモン/ストロベリー/アップル/ワイン/ブランデー/ウィスキー/ラム/
七味/信州味噌/燻製/レモンバーム等)またはTパックタイプのため、データ方針により除外。
残る5銘柄(エチオピア イルガチェフェ、インド モンスーン、グアテマラ オリエンタル、
ブレンド ビター、ブレンド マイルド)のみを対象とする。
バリエーションは「豆」「粉」のみで重量の記載が無い商品が多いが、同店の豆商品は100g売りの
ため(商品名に「100g」と書かれた商品あり)100gとする。価格は「豆」バリエーションのもの。
焙煎度は商品説明の記載(「深煎り」「中煎り」「極浅煎り」等)に基づく。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Alps coffee lAb.",
    "url": "https://alps-coffee-lab.com/",
    "platform": "Shopify",
    "address": "長野県松本市中央2-4-9",
    "prefecture": "長野県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://alps-coffee-lab.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_G = 100

# インフューズド/Tパック商品の判定語(商品名に含まれる場合は除外)
EXCLUDE_WORDS = (
    "Tパック", "パック入り", "燻製", "オレンジ", "レモン", "バナナ", "ストロベリー", "アップル", "リンゴ",
    "ワイン", "ブランデー", "ウィスキー", "ラム", "七味", "味噌", "わさび", "ミント",
)
# 商品説明で確認した焙煎度(handleごと)。(roast_level, roast_hint)
ROAST_BY_HANDLE = {
    "エチオピア-イルガチェフェg1-ナチュラル": ("深煎り", "今回は深煎りでのご提供"),
    "インド-モンスーン": ("中煎り", "中煎りの真ん中で仕上げました"),
    "グアテマラ-オリエンタル-100g": ("浅煎り", "極浅煎り"),
    "ブレンド-ビター-100g": ("深煎り", "深煎り"),
    "ブレンド-マイルド-100g": ("中煎り", "中煎り"),
}
BLEND_COUNTRIES = {"ブレンド-ビター-100g": ["ブラジル", "コロンビア"]}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"[\s　]+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
            continue
        variants = p["variants"]
        variant = next((v for v in variants if v.get("title") == "豆"), variants[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None
        roast_level, roast_hint = ROAST_BY_HANDLE.get(p["handle"], (None, None))

        name = re.sub(r"\s*100g$", "", title).strip()
        parsed = parse_product(name)
        blend_components = []
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            blend_components = [{"origin_country": c} for c in BLEND_COUNTRIES.get(p["handle"], [])]
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
            "roast_level": roast_level,
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
            "price": int(float(variant["price"])),
            "weight_g": WEIGHT_G,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/" + urllib.parse.quote(p["handle"]),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_alpscoffeelab.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_alpscoffeelab.json に出力しました")


if __name__ == "__main__":
    main()
