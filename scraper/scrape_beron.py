# -*- coding: utf-8 -*-
"""
scrape_beron.py

BERON COFFEE ROASTER(beron-coffee.com、新潟県新潟市秋葉区荻島1丁目10-56)の商品情報を
取得する。Shopify(/products.json)。

【対象商品】product_typeが「コーヒー」の8商品(米・穀類は除外)。タイトル末尾の(150g/1P)
から重量を取得し、「豆のまま」バリエーションの価格を採用。焙煎度はタグ(浅煎り/中深煎り)、
なければ説明文の【焙煎】表記。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BERON COFFEE ROASTER",
    "url": "https://beron-coffee.com/",
    "platform": "Shopify",
    "address": "新潟県新潟市秋葉区荻島1丁目10-56",
    "prefecture": "新潟県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://beron-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
ROAST_TAGS = ["中浅煎り", "中深煎り", "浅煎り", "深煎り", "中煎り"]
EXTRA_COUNTRY = {"etiopia": "エチオピア", "ethiopia": "エチオピア"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        m = WEIGHT_PATTERN.search(title)
        weight = int(m.group(1)) if m else None
        name = re.sub(r"\s*\(\s*\d+\s*g[^)]*\)\s*$", "", title).strip()
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", body))

        variants = [v for v in p["variants"] if (v.get("title") or "").startswith("豆のまま")] or p["variants"]
        variant = variants[0]
        available = any(v.get("available") for v in variants)

        roast = None
        for t in p.get("tags", []):
            if t in ROAST_TAGS:
                roast = t
                break
        if not roast:
            rm = re.search(r"【焙煎】\s*(中浅煎り|中深煎り|浅煎り|深煎り|中煎り)", body)
            if rm:
                roast = rm.group(1)
        if not roast and "深煎り" in body[:200]:
            roast = "深煎り"

        pm = re.search(r"(?:PROCESS|【精製】)\s*([A-Za-z][A-Za-z\- ]*?)(?=\s+(?:PROFILE|LOCATION|ALTITUDE|PRODUCE|VARIETY|【)|$)", body)
        fm = re.search(r"(?:Flavour Note|【フレーバー】)\s*:?\s*(?:Flavor\s*[：:])?\s*([^\n]{3,80}?)(?=\s{1,}[^\s/、]{0,20}[ぁ-ヿ一-鿿]{3}|$)", body)
        desc = body[:150] or None
        if fm:
            desc = fm.group(1).strip()
        desc = desc[:80] if desc else None

        parsed = parse_product(name)
        is_blend = "BLEND" in name.upper()
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            c = detect_country_name(name)
            if not c:
                for k, v in EXTRA_COUNTRY.items():
                    if k in name.lower():
                        c = v
            if c and not parsed["origin_country"]:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, " ".join(p.get("tags", [])))

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"] or (pm.group(1).strip() if pm else None),
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
            "product_url": f"{BASE_URL}/products/{quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beron.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beron.json に出力しました")


if __name__ == "__main__":
    main()
