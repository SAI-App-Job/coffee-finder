# -*- coding: utf-8 -*-
"""
scrape_easecoffee.py

ease coffee(easecoffee.jp、千葉県柏市旭町1-7-17 1F。柏市高柳に自家焙煎所のTakayanagi
Roasteryがあるが現在休業中で、実店舗は柏市旭町の1店舗のみ。11店舗未満)の商品情報を
取得する。Shopify。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。公式サイトに「柏市のスペシャルティコーヒー自家焙煎店」
と記載があり、旭町店の住所も確認した。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`は全34件でproduct_typeが
未設定のため、タイトル末尾に焙煎度(「浅煎り」「中煎り」等)が付き、かつ「100g / …」の
バリエーションを持つ商品をコーヒー豆とみなす。器具・ケトル・フィルター・セミナー・シェア
ロースト・卸サンプルセット・Dip Style(ドリップ)・定期便・ギフトセット・
「OMAKASE」業務用1kg(銘柄おまかせ・1kgのみ)は対象外。残る8銘柄(ストレート8、デカフェ1含む)
を収録した。バリエーションは「<重量> / <挽き方> / <フィルター有無>」の組で、最小重量
(すべて100g)の価格を代表とし、100gのバリエーションのいずれかが購入可能なら「販売中」
とする。焙煎度は商品名末尾の記載をroast_levelに移し、名称から除去する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ease coffee",
    "url": "https://easecoffee.jp/",
    "platform": "Shopify",
    "address": "千葉県柏市旭町1-7-17 1F",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://easecoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"^(\d+)\s*[gG]\b")
ROAST_SUFFIX = re.compile(r"\s*(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)\s*$")
EXCLUDE_WORDS = ("セミナー", "セット", "Dip", "ドリップ", "定期便", "OMAKASE")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        roast_m = ROAST_SUFFIX.search(title)
        if not roast_m or any(w in title for w in EXCLUDE_WORDS):
            continue
        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.match((v.get("title") or "").strip())
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, v in weighted)
        smallest = [v for w, v in weighted if w == weight]
        price = min(int(float(v["price"])) for v in smallest)
        available = any(v.get("available") for v in smallest)

        name = ROAST_SUFFIX.sub("", title)
        roast_level = roast_m.group(1)
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

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
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_easecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_easecoffee.json に出力しました")


if __name__ == "__main__":
    main()
