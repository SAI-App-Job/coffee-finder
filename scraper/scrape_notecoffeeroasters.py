# -*- coding: utf-8 -*-
"""
scrape_notecoffeeroasters.py

note coffee roasters(www.kakuou-note.com、愛知県名古屋市千種区楠元町2丁目32-1、覚王山の
自家焙煎店)の商品情報を取得する。Shopify。
※既存の「coffee beans & tools note」(scrape_coffeenote.py)とは別の店舗。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「コーヒー豆」の5商品(シングル3・ブレンド2、うちデカフェ1)を対象とする。バリエーションは
「<重量> / <豆のまま・粉に挽いて>」の組で、最小重量(100g)の価格を代表とする。
焙煎度は商品説明の「【焙煎度合い】」、味わいは「【tastingnote】」から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "note coffee roasters",
    "url": "https://www.kakuou-note.com/",
    "platform": "Shopify",
    "address": "愛知県名古屋市千種区楠元町2丁目32-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://www.kakuou-note.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def field(body: str, label: str) -> str | None:
    m = re.search(r"【" + label + r"】\s*([^\n【]+)", body)
    return m.group(1).strip() if m else None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title or "ドリップバッグ" in title:
            continue

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        roast = field(body, "焙煎度合い")
        if not roast:
            rm = re.search(r"焙煎[：:]\s*([^\n]+)", body)
            if rm:
                roast = re.sub(r"のブレンド$", "", rm.group(1).strip())
        tasting = field(body, "tastingnote")
        if not tasting:
            tm = re.search(r"<当店の焙煎により感じられるフレーバー>\s*\n([^\n]+)", body)
            if tm:
                tasting = tm.group(1).strip()
        if not tasting:
            bm = re.search(r"ブレンドの特徴[：:]\s*([^\n]+)", body)
            if bm:
                tasting = bm.group(1).strip()
        process = field(body, "プロセス")
        farm = field(body, "生産者")
        area = field(body, "エリア")
        farm_note = " / ".join(x for x in (farm, area) if x) or None

        parsed = parse_product(title)
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        processing = parsed["processing_method"]
        if not processing and process:
            from coffee_parser import detect_processing_method
            processing = detect_processing_method(process) or None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": tasting,
            "farm_note": farm_note,
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
    with open("data_notecoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_notecoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
