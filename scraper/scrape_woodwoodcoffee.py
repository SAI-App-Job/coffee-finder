# -*- coding: utf-8 -*-
"""
scrape_woodwoodcoffee.py

WoodWood Coffee Roast Service(woodwood.coffee、福井県福井市成和1-2231 WWビル1F)の
商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「コーヒー豆」の24商品(シングル・ブレンド・デカフェ)を対象とする。器具・グッズ・
ギフト・ドリップバッグ・コーヒー製品・定期便は除外。バリエーションは
「豆のまま / 150g」「豆のまま / 500g」「粉にする / 150g」等で、「豆のまま」の
最小重量(150g)を代表とする。商品名は「銘柄【焙煎度】説明文 150g/500g」形式のため、
「銘柄【焙煎度】」を商品名とし、説明文は flavor_notes に回す。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "WoodWood Coffee Roast Service",
    "url": "https://woodwood.coffee/",
    "platform": "Shopify",
    "address": "福井県福井市成和1-2231 WWビル1F",
    "prefecture": "福井県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://woodwood.coffee"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
TITLE_PATTERN = re.compile(r"^(.*?)【([^】]*)】(.*)$")


def clean_title(title: str):
    """(商品名, 焙煎度, タイトル末尾の説明文) を返す。"""
    title = unicodedata.normalize("NFC", re.sub(r"\s+", " ", title)).strip()
    title = re.sub(r"\s*150g/500g\s*$", "", title)
    m = TITLE_PATTERN.match(title)
    if not m:
        return title, None, None
    head, inner, tail = m.group(1).strip().rstrip("・ "), m.group(2), m.group(3).strip()
    rm = ROAST_PATTERN.search(inner)
    roast = rm.group(1) if rm else None
    note = (inner.replace(roast, "").strip("・ ") if roast else inner) or None
    if tail:
        note = f"{note} {tail}".strip() if note else tail
    name = f"{head}【{roast}】" if roast else head
    return name, roast, note


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        name, roast, note = clean_title(p["title"])

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "豆のまま" not in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = unicodedata.normalize("NFC", re.sub(r"\s+", " ", body))
        desc = (note + " " if note else "") + body
        desc = desc.strip()[:400] or None

        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        if "ブレンド" in name or "Blend" in name or "Kiwami" in name or "Dark Jungle" in name \
                or "Wood Terrace" in name or "Sunbeams" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["origin_country"] and name.startswith("ウガンダ"):
                parsed["origin_country"] = "ウガンダ"
                parsed["origin_source"] = "raw_name"

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
    with open("data_woodwoodcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_woodwoodcoffee.json に出力しました")


if __name__ == "__main__":
    main()
