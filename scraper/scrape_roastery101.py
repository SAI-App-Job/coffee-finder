# -*- coding: utf-8 -*-
"""
scrape_roastery101.py

COFFEE ROASTERY 101(珈琲屋101、shop.roastery101.com、愛知県一宮市玉野字大崎10-1)の
オンラインショップの商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「コーヒー豆」の商品のみを対象とする(ブレンド・シングルオリジンの焙煎豆)。
「コーヒー豆定期便」「ドリップバッグ」「コーヒー器具」(サイフォン器具等)は除外。
重量は商品名末尾の「【100g】」「【200g】」表記による(1商品1サイズ。バリエーションは
挽き方のみ)。価格は同一商品内で挽き方によらず同額。焙煎度はバリエーション
オプション「Roast Level(焙煎度)」の値(例:「Medium(浅煎り)」)を採用し、括弧内の
日本語表記があればそれを、なければ英語表記を正規名称に変換して用いる。
在庫は、いずれかのバリエーションが購入可能なら「販売中」とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "COFFEE ROASTERY 101",
    "url": "https://shop.roastery101.com/",
    "platform": "Shopify",
    "address": "愛知県一宮市玉野字大崎10-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.roastery101.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_IN_TITLE = re.compile(r"【\s*(\d+)\s*g\s*】")
COUNTRY_PREFIX = re.compile(r"^【([^】]+)】\s*")
ROAST_JA = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_EN = {"light": "ライトロースト", "medium": "ミディアムロースト", "high": "ハイロースト", "city": "シティロースト"}


def roast_level_of(p: dict) -> str | None:
    for v in p["variants"]:
        for opt in (v.get("option1"), v.get("option2"), v.get("option3")):
            if not opt or "（" not in opt and not re.match(r"^(Light|Medium|High|City)", opt, re.I):
                continue
            if re.search(r"Whole|fine|coarse|挽き", opt, re.I) and not ROAST_JA.search(opt):
                continue
            m = ROAST_JA.search(opt)
            if m:
                return m.group(1)
            m2 = re.match(r"^(Light|Medium|High|City)", opt, re.I)
            if m2:
                return ROAST_EN[m2.group(1).lower()]
    return None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(w in title for w in ("定期便", "ドリップバッグ", "DRIP BAG", "セット")):
            continue
        wm = WEIGHT_IN_TITLE.search(title)
        weight = int(wm.group(1)) if wm else None
        name = WEIGHT_IN_TITLE.sub("", title).strip()
        cm = COUNTRY_PREFIX.match(name)
        country_hint = cm.group(1) if cm else None
        name = COUNTRY_PREFIX.sub(lambda m: m.group(1) + " ", name).strip()

        variants = p["variants"]
        available = any(v.get("available") for v in variants)
        price = int(float(min(variants, key=lambda v: float(v["price"]))["price"]))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        fm = re.search(r"Flavor profile\s*\n?\s*([^\n]+)", body, re.I)
        flavor = fm.group(1).strip().rstrip("、,") if fm else None
        roast = roast_level_of(p)
        if not roast:
            rm = re.search(r"Roast level\s*\n?\s*([A-Za-z ]+)", body, re.I)
            if rm:
                key = rm.group(1).strip().split()[0].lower()
                roast = ROAST_EN.get(key)

        parsed = parse_product(name)
        if "blend" in name.lower() or "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, country_hint or "")

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
            "flavor_notes": flavor or (re.sub(r"\s+", " ", body)[:300] or None),
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
    with open("data_roastery101.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roastery101.json に出力しました")


if __name__ == "__main__":
    main()
