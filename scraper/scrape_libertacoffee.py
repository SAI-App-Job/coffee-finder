# -*- coding: utf-8 -*-
"""
scrape_libertacoffee.py

リベルタコーヒー(www.libertacoffeeshop.com、福岡県中間市中尾1-17-13の自家焙煎コーヒー店)の
商品情報を取得する。WooCommerce(Store API `/wp-json/wc/store/v1/products`、63商品)。

【対象商品について】
実データ確認済み(2026-10時点): 通常の焙煎豆(ブレンド: リベルタブレンド/ソフトブレンド/ビターブレンド/
No Trends、デカフェ ブラジル、スペシャルティの「コスタリカ ガンボア」)が、重量違い(100g/200g/300g/500g)の
別商品として並ぶ。銘柄ごとに最小重量(100g)の商品を代表にする。
次は対象外: 「(post便)」(ポスト投函コーヒー便)の同名商品(通常商品と重複する別販売形態)、
ポスト投函コーヒー便のセット・挽き方選択の商品、卸売専用・取引先名(【フラッティ様】等)の商品、
ドリップバッグ、水出しコーヒーバッグ、飲み比べセット、器具(コーヒープレス)。

【価格・重量・在庫】
重量は商品名末尾の「100g」から、価格・在庫はStore APIの商品価格・is_in_stock(挽き方のみの
バリエーションで価格差なし)を使う。店は浅煎りを扱わない方針で焙煎度の明記が無いため、
説明文に「中深煎り/深煎り/中煎り」があれば取得し、無ければnull。
ブレンドは商品名の「ブレンド」(No Trendsは説明文の「ブレンド」)で判定。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
)

SHOP_INFO = {
    "name": "リベルタコーヒー",
    "url": "https://www.libertacoffeeshop.com/",
    "platform": "WooCommerce",
    "address": "福岡県中間市中尾1-17-13",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認(WooCommerce標準構成)",
}

BASE_URL = "https://www.libertacoffeeshop.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = (
    "post便", "ポスト投函", "様", "さま", "卸売", "ドリップ", "水出し", "セット", "プレス", "挽き", "選択なし", "豆のまま",
    "飲み比べ", "のみの方",
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
NAME_TRAIL_PATTERN = re.compile(r"\s*\d+\s*(?:kg|g)\s*$", re.I)
ROAST_PATTERN = re.compile(r"(中深煎り|中煎り|深煎り)")
EXTRA_BLEND_NAMES = ("No Trends",)


def fetch_all_products() -> list[dict]:
    products = []
    for page in range(1, 10):
        resp = requests.get(
            f"{BASE_URL}/wp-json/wc/store/v1/products?per_page=100&page={page}",
            headers=REQUEST_HEADERS, timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products += batch
        if len(batch) < 100:
            break
    return products


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True))


def scrape_all_products() -> list[dict]:
    best: dict[str, dict] = {}
    for p in fetch_all_products():
        title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", BeautifulSoup(p["name"], "html.parser").get_text())).strip()
        if any(k in title for k in EXCLUDE_KEYWORDS):
            continue
        if any("卸売" in c["name"] or "様" in c["name"] for c in p.get("categories", [])):
            continue
        wm = WEIGHT_PATTERN.search(title)
        price = int(p["prices"]["price"] or 0)
        if not wm or price <= 0:
            continue
        # 1kg等の取引先向け・卸売は除外済み。重量(g)に換算
        weight = int(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)
        key = NAME_TRAIL_PATTERN.sub("", title).strip()
        if key in best and best[key]["weight_g"] <= weight:
            continue

        short_text = text_of(p.get("short_description"))
        desc_text = text_of(p.get("description"))
        flavor_notes = (desc_text or short_text)[:400] or None
        in_stock = bool(p.get("is_in_stock"))

        parsed = parse_product(key)
        is_blend = "ブレンド" in key or key in EXTRA_BLEND_NAMES
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            parsed["processing_method"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(key)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, key)
            if not parsed["processing_method"] and "ブラックハニー" in short_text:
                parsed["processing_method"] = "ハニー"
        rm = ROAST_PATTERN.search(key) or ROAST_PATTERN.search(short_text) or ROAST_PATTERN.search(desc_text)
        roast_level = rm.group(1) if rm else parsed["roast_level"]

        best[key] = {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_level,
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": p["permalink"],
        }
    return list(best.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_libertacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_libertacoffee.json に出力しました")


if __name__ == "__main__":
    main()
