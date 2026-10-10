# -*- coding: utf-8 -*-
"""
scrape_marutecoffee.py

マルテ珈琲焙煎所(https://shop.marutecoffee.com、長野県上高井郡小布施町小布施788)の
商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`はproduct_typeが空のため、
バリエーションが「<重量>g / 豆」形式のコーヒー豆商品だけを対象とする。ドリップバッグ・
水出しコーヒーバッグ・ギフト・セット商品はバリエーションが「なし」「あり(無料)」等のため
自動的に除外される(念のためタイトルでも除外)。重量違い(100g/200g/500g)・挽き方違いの
バリエーションのうち、最小重量(100g)の「豆」の価格を代表とする。
焙煎度は商品名、なければ説明文の「焙煎:」表記から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "マルテ珈琲焙煎所",
    "url": "https://shop.marutecoffee.com/",
    "platform": "Shopify",
    "address": "長野県上高井郡小布施町小布施788",
    "prefecture": "長野県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://shop.marutecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_WORDS = ("ドリップバッグ", "ギフト", "セット", "水出し", "バッグ")
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)
ROAST_LABEL_PATTERN = re.compile(r"焙煎\s*[:：]\s*(\S+)")
# 商品名・説明文の「産地:」が国名でない商品の産地(説明文で確認済み: 産地「ベンチ・マジ」=エチオピアのゲイシャ)
ORIGIN_OVERRIDES = {"ethiopia-geisha-lightroast": "エチオピア"}
ORIGIN_LABEL_PATTERN = re.compile(r"産地\s*[:：]\s*([^\s]+(?:[、,][^\s、,]+)*)")


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
            continue
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.match(vt)
            if m and vt.rstrip().endswith("豆"):
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        intro = re.split(r"苦味\s*[:：]", body)[0].strip()
        desc = intro[:400] or None

        roast_level, roast_hint = coarse_roast(title)
        if not roast_level:
            m = ROAST_LABEL_PATTERN.search(body)
            if m:
                roast_level, roast_hint = coarse_roast(m.group(1))
                if roast_hint and "＋" in m.group(1):
                    # 「中煎り＋浅煎り」(オブセブレンド秋)は2段階の混合焙煎のため中浅煎りとし、原文を hint に残す
                    roast_level, roast_hint = "中浅煎り", m.group(1)

        parsed = parse_product(title)
        blend_components = []
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            m = ORIGIN_LABEL_PATTERN.search(body)
            if m:
                for part in re.split(r"[、,]", m.group(1)):
                    c = detect_country_name(part)
                    if c:
                        blend_components.append({"origin_country": c})
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"]:
                m = ORIGIN_LABEL_PATTERN.search(body)
                c = detect_country_name(m.group(1)) if m else None
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)
            if p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "description"
        decaf_process = None
        if "ディカフェ" in title and "マウンテンウォーター" in body:
            decaf_process = "マウンテンウォータープロセスによりカフェインを除去"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_hint,
            "decaf_process": decaf_process,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
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
    with open("data_marutecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_marutecoffee.json に出力しました")


if __name__ == "__main__":
    main()
