# -*- coding: utf-8 -*-
"""
scrape_dayscoffeeroaster.py

Days Coffee Roaster(dayscoffeeroaster.jp、新潟県新潟市中央区女池神明3-14-4
NEST MEIKE SHINMEI(女池店))の商品情報を取得する。Shopify(/products.json)。

【対象商品】product_typeが「コーヒー豆」の商品のみ(リキッドコーヒー・ボトル・Tシャツ・
化粧箱・卸専用は除外)。説明文に「インフューズド」「インフュージョン」を含む商品
(STRAWBERRY CANDY、VANILLA OAK BARREL)は除外。バリエーションは「豆のまま/ペーパー用」
で価格は共通。重量は商品名の【100g】等から取得する。焙煎度はタグ(浅煎り/中煎り/深煎り)。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Days Coffee Roaster",
    "url": "https://dayscoffeeroaster.jp/",
    "platform": "Shopify",
    "address": "新潟県新潟市中央区女池神明3-14-4 NEST MEIKE SHINMEI(女池店)",
    "prefecture": "新潟県",
    "robots_txt_status": "確認済み(Shopify標準構成、products.jsonは公開)",
}

BASE_URL = "https://dayscoffeeroaster.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"【\s*(\d+)\s*g\s*】", re.I)
LABELS = "原産国|標高|品種|精製方法|収穫年度|特徴|風味特性"
INFUSED = re.compile(r"インフューズド|インフュージョン|インフュージョン|infus", re.I)
ROAST_TAGS = {"浅煎り": "浅煎り", "中煎り": "中煎り", "深煎り": "深煎り", "中深煎り": "中深煎り", "中浅煎り": "中浅煎り"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title:
            continue
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        if INFUSED.search(body) or INFUSED.search(title):
            continue

        m = WEIGHT_PATTERN.search(title)
        weight = int(m.group(1)) if m else None
        variants = [v for v in p["variants"] if (v.get("title") or "").startswith("豆のまま")] or p["variants"]
        variant = variants[0]
        available = any(v.get("available") for v in variants)
        name = re.sub(r"\s*【\d+\s*g】\s*", "", title).strip()

        roast = None
        for t in p.get("tags", []):
            k = t.split("/")[0].strip()
            if k in ROAST_TAGS:
                roast = ROAST_TAGS[k]
                break

        feature = None
        fm = re.search(r"(?:特徴|風味特性)\s*[：:]\s*([^\s・、]+(?:\s*[・、]\s*[^\s・、]+)*)", body)
        if fm:
            feature = fm.group(1)

        def field(label):
            mm = re.search(label + r"\s*[：:]\s*(.+?)(?=\s(?:" + LABELS + r")\s*[：:]|\s{2,}|$)", body)
            return mm.group(1).strip()[:60] if mm else None

        origin_field = field("原産国") or ""
        origin_field = unicodedata.normalize("NFKC", origin_field)
        process_field = field("精製方法")
        if process_field:
            process_field = re.sub(r"(?<=[ぁ-ヿ一-鿿])\s+(?=[ぁ-ヿ一-鿿])", "", process_field)

        parsed = parse_product(name)
        is_blend = "ブレンド" in name or "BLEND" in name.upper() or "/" in origin_field
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            c = detect_country_name(origin_field) or detect_country_name(name)
            if not c and origin_field.strip() == "中国":
                c = "中国"
            if c and not parsed["origin_country"]:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, origin_field)
        decaf = "DECAF" in name.upper()

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"] or process_field,
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": feature or (body[:400] or None),
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"] + (["デカフェ"] if decaf and "デカフェ" not in parsed["post_processing_tags"] else []),
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
    with open("data_dayscoffeeroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dayscoffeeroaster.json に出力しました")


if __name__ == "__main__":
    main()
