# -*- coding: utf-8 -*-
"""
scrape_funnelcoffeeroasters.py

Funnel Coffee Roasters(公式 https://www.funnelcoffee.jp 、長野県北佐久郡御代田町塩野400-158)の
商品情報を取得する。販売は親会社pace aroundのShopifyストア(https://pacearound.com)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「ブレンド」
「シングルオリジン」の商品(ブレンド3・シングル4の計7件)のみを対象とする。パン・菓子・
雑貨・ギフトラッピングは除外。バリエーションは「200g / <挽き方>」で全て200g・同価格のため、
「豆のまま」の価格を採用する。焙煎度は商品名(シングル)または説明文(普賢ブレンドの
「深煎りを追求」)に基づき、記載の無い高峰・碓氷ブレンドはNone。
シングルのhandleは使い回しで商品名と食い違う(例: マンデリンのhandleが「エチオピア-中煎り」)
ため、商品名・説明文を正とする。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "Funnel Coffee Roasters",
    "url": "https://www.funnelcoffee.jp/",
    "platform": "Shopify",
    "address": "長野県北佐久郡御代田町塩野400-158",
    "prefecture": "長野県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://pacearound.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = ("ブレンド", "シングルオリジン")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)
BLEND_CONTENT_PATTERN = re.compile(r"ブレンド内容\s*([^\s]+(?:[、,]\s*[^\s、,]+)*)")
FIELD_PATTERN = {
    "farm": re.compile(r"農\s*園\s*名\s*(\S+(?: \S+)*?)\s+標"),
    "area": re.compile(r"エ\s*リ\s*ア\s*(.+?)\s+農\s*園"),
    "altitude": re.compile(r"標\s*高\s*(\S+)"),
    "variety": re.compile(r"品\s*種\s*(.+?)\s*生産処理"),
    "process": re.compile(r"生産処理\s*(?:生産処理\s*)?(\S+)"),
}
# 説明文中で「国名」ではなく別表記の産地(ブレンド内容は「グァテマラ」表記)
COUNTRY_ALIASES = {"グァテマラ": "グアテマラ", "マンデリン": "インドネシア"}


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
        if p.get("product_type") not in BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.match(vt)
            if m and "豆のまま" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None

        roast_level, roast_hint = coarse_roast(title)
        if not roast_level and p["product_type"] == "ブレンド":
            roast_level, roast_hint = coarse_roast(body)

        parsed = parse_product(title)
        blend_components = []
        farm_note = None
        if p["product_type"] == "ブレンド" or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            m = BLEND_CONTENT_PATTERN.search(body)
            if m:
                for part in re.split(r"[、,]", m.group(1)):
                    part = COUNTRY_ALIASES.get(part.strip(), part.strip())
                    c = detect_country_name(part)
                    if c:
                        blend_components.append({"origin_country": c})
        else:
            parsed["category"] = "ストレート"
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            parts = []
            for label, key in (("エリア", "area"), ("農園", "farm"), ("標高", "altitude"), ("品種", "variety")):
                m = FIELD_PATTERN[key].search(body)
                if m:
                    parts.append(f"{label}: {m.group(1).strip()}")
            farm_note = " / ".join(parts) or None
            m = FIELD_PATTERN["process"].search(body)
            if m and not parsed["processing_method"]:
                parsed["processing_method"] = detect_processing_method(m.group(1)) or m.group(1)

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
            "flavor_notes": desc,
            "farm_note": farm_note,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/" + urllib.parse.quote(p["handle"]),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_funnelcoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_funnelcoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
