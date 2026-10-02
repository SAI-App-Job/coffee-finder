# -*- coding: utf-8 -*-
"""
scrape_sevenstepscoffee.py

SEVEN STEPS COFFEE CLUB(sevenstepscoffeeclub.com、千葉県千葉市稲毛区黒砂台1-11-21
高橋ビル1G。ギーセン6kg焙煎機で自家焙煎するスペシャルティロースタリー。店舗は1店舗のみで
11店舗未満)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。公式サイトのトップで千葉市稲毛区の店舗住所と
「ギーセン6kg焙煎機で焙煎」の記載を確認した。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`(plain requestsで取得可)のうち
product_typeが「COFFEE BEANS」の商品から、ドリップバッグ(タイトルが「DRIP BAG」始まり)を
除いたコーヒー豆7銘柄(ストレート6・ブレンド1、デカフェ1含む)を対象とする。Tシャツ等
(GOODS)は除外。バリエーションは「<重量> / <挽き方>」の組で、最小重量(100g)の価格を
代表とする(200g以上は割引が付くが別サイズのため対象外)。在庫は100gのバリエーションの
いずれかが購入可能なら「販売中」とする。商品名は「生産者/銘柄/国/精製」形式のため、
産地は名前中の英語国名から判定し、焙煎度は名称内の「深煎り」「中煎り」、なければ説明文の
「Roast:Light/Medium/Dark」から決める(Nigusse Gemeda商品のみ説明文が「Roast:Light」だが
本文・タイトルとも「深煎り」のため深煎りとする)。BLACK STARはブレンド表記が無いが
「深煎りのブレンド」との説明のためブレンドとして扱う。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "SEVEN STEPS COFFEE CLUB",
    "url": "https://sevenstepscoffeeclub.com/",
    "platform": "Shopify",
    "address": "千葉県千葉市稲毛区黒砂台1-11-21 高橋ビル1G",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://sevenstepscoffeeclub.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "COFFEE BEANS"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_IN_TITLE = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_IN_BODY = re.compile(r"Roast\s*[:：]\s*(Light|Medium|Dark)", re.I)
ROAST_MAP = {"light": "浅煎り", "medium": "中煎り", "dark": "深煎り"}

# 名称に「ブレンド」等の表記が無いがブレンドと説明されている商品(ハンドル→True)
BLEND_HANDLES = {"black-star"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if title.upper().startswith("DRIP BAG") or "セット" in title:
            continue

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.match(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, v in weighted)
        smallest = [v for w, v in weighted if w == weight]
        price = min(int(float(v["price"])) for v in smallest)
        available = any(v.get("available") for v in smallest)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        name = title.replace("★", "").strip()
        roast_level = None
        m = ROAST_IN_TITLE.search(name)
        if m:
            roast_level = m.group(1)
        else:
            m = ROAST_IN_BODY.search(body)
            if m:
                roast_level = ROAST_MAP[m.group(1).lower()]

        parsed = parse_product(name)
        if p["handle"] in BLEND_HANDLES:
            parsed["category"] = "ブレンド"
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
            "roast_level": roast_level or parsed["roast_level"],
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
    with open("data_sevenstepscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sevenstepscoffee.json に出力しました")


if __name__ == "__main__":
    main()
