# -*- coding: utf-8 -*-
"""
scrape_citekyoto.py

cité 京都自家焙煎コーヒースタンド(cite-kyoto.myshopify.com、京都府京都市下京区
紺屋町375-4)の商品情報を取得する。Shopify。

【対象商品について】
Shopifyの`/products.json`の全8銘柄(シングルオリジン7+ブレンド1)が焙煎豆。
バリエーションは「<重量>g / Whole Beans(豆のまま) / Filter(粉)」の組で、
最小重量(90g、Ethiopia Gotitiのみ150g、Medium Blendは150g)のバリエーションを代表と
する。在庫は同重量のいずれか(豆のまま・粉)が購入可能なら販売中とする。商品説明に「REGION / PRODUCER / ROAST LEVEL / PROCESS / VARIETIES / TASTING
NOTES」の構造化表記があるため、焙煎度・精製方法・生産者・品種・テイスティングノートを
そこから取得する(実データ確認済み)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           normalize_processing_method, detect_processing_method)

SHOP_INFO = {
    "name": "cité 京都自家焙煎コーヒースタンド",
    "url": "https://cite-kyoto.myshopify.com/",
    "platform": "Shopify",
    "address": "京都府京都市下京区紺屋町375-4",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://cite-kyoto.myshopify.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
EXCLUDE_KEYWORDS = ("セット", "ドリップバッグ", "定期便", "ギフト", "gift", "set")
ROAST_MAP = {
    "light": "浅煎り", "medium light": "中浅煎り", "medium": "中煎り",
    "medium dark": "中深煎り", "dark": "深煎り",
}
ROAST_PATTERN = re.compile(r"ROAST LEVEL[^A-Za-z]*([A-Za-z ]+?)\s*Roast", re.I)
PROCESS_PATTERN = re.compile(r"PROCESS[^A-Za-z]*/\s*(.+?)\s*VARIETIES", re.S)
VARIETY_PATTERN = re.compile(r"VARIETIES[^A-Za-z]*/\s*(.+?)\s*ALTITUDE", re.S)
PRODUCER_PATTERN = re.compile(r"PRODUCER[^A-Za-z]*/\s*(.+?)\s*ROAST LEVEL", re.S)
BLEND_PATTERN = re.compile(r"(\d+)%\s*([A-Za-z ]+?)\s*[,/]")
NOTES_PATTERN = re.compile(r"TASTING NOTES\s*/\s*(.+?)(?:#|焙煎日から|$)", re.S)


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    seen = set()
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
            continue
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        soup = BeautifulSoup(p.get("body_html") or "", "html.parser")
        body = re.sub(r"\s+", " ", soup.get_text("", strip=True))
        body_sp = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

        parsed = parse_product(title)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        roast_level = None
        m = ROAST_PATTERN.search(body)
        if m:
            roast_level = ROAST_MAP.get(m.group(1).strip().lower())

        processing = parsed["processing_method"]
        m = PROCESS_PATTERN.search(body)
        if m:
            processing = normalize_processing_method(m.group(1).strip())

        farm_parts = []
        m = PRODUCER_PATTERN.search(body)
        if m:
            farm_parts.append("生産者: " + m.group(1).strip())
        m = VARIETY_PATTERN.search(body)
        if m:
            farm_parts.append("品種: " + m.group(1).strip())
        farm_note = " / ".join(farm_parts) or None

        notes = None
        m = NOTES_PATTERN.search(body_sp)
        if m:
            notes = m.group(1).strip()
        if not notes:
            notes = body_sp[:300] or None

        blend_components = []
        for pct, region in BLEND_PATTERN.findall(body_sp):
            c = detect_country_name(region)
            if c:
                blend_components.append({"origin_country": c, "percentage": int(pct)})

        url = f"{BASE_URL}/products/{p['handle']}"
        if url in seen:
            continue
        seen.add(url)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
            "flavor_notes": notes,
            "farm_note": farm_note,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_citekyoto.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_citekyoto.json に出力しました")


if __name__ == "__main__":
    main()
