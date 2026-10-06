# -*- coding: utf-8 -*-
"""
scrape_gakuzancoffee.py

岳山珈琲(GAKUZAN COFFEE、https://shop.gakuzancoffee.com/、宮城県仙台市泉区福岡字岳山7-101
本店)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(宮城県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうちproduct_typeが「コーヒー豆」の
焙煎豆(シングルオリジン・ブレンド)を対象とする。「いろいろセット・セレクト定期便」
(セット・定期便)は除外。カップオンコーヒー・水出しパック・スターターセット・短期サブスク
(product_typeが別)も除外。
バリエーションは挽き方違い(豆のまま/中細挽き/中挽き)のみで重量は含まれないため、
重量はタイトルの「100g」表記、無ければ商品説明中の最初の「<数字>g」(通常200g)から取得する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "岳山珈琲",
    "url": "https://shop.gakuzancoffee.com/",
    "platform": "Shopify",
    "address": "宮城県仙台市泉区福岡字岳山7-101",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.gakuzancoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
EXCLUDE_KEYWORDS = ("セット", "定期", "サブスク")
WEIGHT_PATTERN = re.compile(r"([0-9０-９]+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")


def coarse_roast(text: str | None) -> str | None:
    """「深煎」「中深煎」等の表記を「〜煎り」に統一して返す。"""
    if not text:
        return None
    m = ROAST_PATTERN.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    r = m.group(1)
    return r if r.endswith("り") else r + "り"


def clean_title(title: str) -> str:
    """【岳山珈琲】・末尾の「岳山珈琲」と、「｜」以降のキャッチコピーを落とす(焙煎度だけの短い区間は残す)。"""
    t = re.sub(r"\s+", " ", title.replace("　", " ").replace("【岳山珈琲】", "")).strip()
    parts = [p.strip() for p in t.split("｜")]
    kept = [parts[0]]
    for p in parts[1:]:
        if len(p) <= 8 and ROAST_PATTERN.search(p):
            kept.append(p)
    t = " ".join(kept)
    t = re.sub(r"\s*岳山珈琲\s*$", "", t)
    t = WEIGHT_PATTERN.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def find_weight(text: str) -> int | None:
    m = WEIGHT_PATTERN.search(text)
    return int(unicodedata.normalize("NFKC", m.group(1))) if m else None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        if any(k in p["title"] for k in EXCLUDE_KEYWORDS):
            continue
        name = clean_title(p["title"])

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        weight = find_weight(p["title"]) or find_weight(body)
        # 最小重量はバリエーション間で共通(挽き方違いのみ)のため、最安の価格のバリエーションではなく先頭を代表とする
        variant = p["variants"][0]
        available = any(v.get("available") for v in p["variants"])
        desc = body[:400] or None

        parsed = parse_product(name)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["grade"] = None
            parsed["designated_brand"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["processing_method"]:
                parsed["processing_method"] = extract_from_description(body.replace(" 精選方法", "\n精選方法"))["processing_method"]

        roast = coarse_roast(name) or parsed["roast_level"]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
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
    with open("data_gakuzancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gakuzancoffee.json に出力しました")


if __name__ == "__main__":
    main()
