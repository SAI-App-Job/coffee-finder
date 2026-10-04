# -*- coding: utf-8 -*-
"""
scrape_aligncoffee.py

ALIGN COFFEE ROASTER(aligncoffeeroaster.com、兵庫県姫路市坂田町40)の商品情報を取得する。
Shopify。旧BASE版(shop.aligncoffeeroaster.com)は使わない。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`は全20件でproduct_typeが全て空。うち
タイトルが「【浅煎り】」「【中深煎り】」「［中深煎り］」等で始まる焙煎豆16件(シングル
オリジン、同一豆の浅煎り・中深煎り違いは別商品として別ハンドル)を対象とし、
「定期便」4件(【コーヒー豆の定期便 〜】)は除外する。ブレンドの取扱いは確認できなかった。
バリエーションは「<重量> / 豆のまま|粉に挽く」の組で、豆のままの最小重量(多くは50g)の
価格・在庫を代表とする(50g/100g/150g等から選択可能)。

【価格について】
商品ページに「¥1,400 (税込)」と表示されており、`products.json`のpriceは税込。

【焙煎度について】
タイトル冒頭の「【浅煎り】」「【中深煎り】」はプロ向け8段階表記ではないため
roast_levelには反映せずroast_hintとして保持する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ALIGN COFFEE ROASTER",
    "url": "https://aligncoffeeroaster.com/",
    "platform": "Shopify",
    "address": "兵庫県姫路市坂田町40",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://aligncoffeeroaster.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["定期便", "セット", "ギフト", "ドリップバッグ"]
ROAST_PREFIX = re.compile(r"^[【\[［]\s*(浅煎り|中煎り|中深煎り|深煎り|中浅煎り)\s*[】\]］]\s*")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    products, page = [], 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
    return products


def pick_variant(p: dict):
    cands = []
    for v in p["variants"]:
        t = v.get("title") or ""
        if "粉" in t:
            continue
        m = WEIGHT_PATTERN.search(t)
        if m:
            cands.append((int(m.group(1)), v))
    if not cands:
        return None
    return min(cands, key=lambda x: x[0])


def build_record(p: dict) -> dict | None:
    title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    pm = ROAST_PREFIX.match(title)
    if not pm:
        return None
    roast_hint = pm.group(1)
    picked = pick_variant(p)
    if not picked:
        return None
    weight, variant = picked
    name = title

    body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body)
    desc = body.split("【STORY】")[0].strip()[:400] or None

    bare = ROAST_PREFIX.sub("", title)
    parsed = parse_product(bare)
    if "ブレンド" in bare or "blend" in bare.lower():
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(bare)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, bare)
        if parsed["origin_country"] == "ドミニカ国":
            # 「Dominica Princesa」はドミニカ共和国(アルフレド・ディアス農園)産。商品説明で確認済み
            parsed["origin_country"] = "ドミニカ共和国"
            parsed["origin_source"] = "raw_name"

    available = bool(variant.get("available"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/products/{p['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_aligncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_aligncoffee.json に出力しました")


if __name__ == "__main__":
    main()
