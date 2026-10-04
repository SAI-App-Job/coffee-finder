# -*- coding: utf-8 -*-
"""
scrape_ashiyaevian.py

芦屋エビアンコーヒーショップ(ashiya-evian-coffee-shop.com、兵庫県芦屋市茶屋之町11-8、
昭和42年(1967年)創業の自家焙煎コーヒー店)の商品情報を取得する。Shopify。
神戸のEVIAN(別店舗)とは無関係。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`は42件でproduct_typeは全て空。うち
「100g / 豆のまま」バリエーションを持つ焙煎豆13件(ブレンド5種=ORIGINAL/MILD/DARK/
CLASSIC/NUT、シングルオリジン7種=ケニア/メキシコ/エチオピア/グアテマラ/ブラジル/
マンデリン/コロンビア、デカフェ1種=コロンビア・スイスウォータープロセス)を対象とする。
以下は除外する: ギフトボックス全般、ドリップバッグ、ダンクコーヒー、コーヒーベース、
ウイスキーコーヒー(ウイスキーに漬け込んだ香り付けコーヒーのため)、紅茶・ティーバッグ、
ミル、麻袋、Tシャツ、オーツミルク・チャイ等の飲料。
バリエーションは「100g / 豆のまま|粗挽き|中挽き|中細挽き」で、豆のままのバリエーションの
価格・在庫を代表とする(全商品の最小重量が100g)。

【価格について】
商品ページに「税込」の表記あり(`products.json`のpriceは税込)。

【産地・焙煎度について】
商品説明の「原材料名」に産地(シングルオリジン)が、カッピングコメントに焙煎度
(フルシティー/イタリアンロースト等)が記載されている場合のみ取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "芦屋エビアンコーヒーショップ",
    "url": "https://ashiya-evian-coffee-shop.com/",
    "platform": "Shopify",
    "address": "兵庫県芦屋市茶屋之町11-8",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://ashiya-evian-coffee-shop.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = [
    "GIFT", "ギフト", "DRIP", "ドリップ", "DUNK", "ダンク", "BASE", "ベース", "WHISKY", "ウイスキー",
    "TEA", "ティー", "MILL", "ミル", "DONGOROS", "ドンゴロス", "Tシャツ", "MILK", "ミルク", "チャイ",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティー?|シティー?|フレンチ|イタリアン)ロースト")


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
        if "豆のまま" not in t:
            continue
        m = WEIGHT_PATTERN.search(t)
        if m:
            cands.append((int(m.group(1)), v))
    if not cands:
        return None
    return min(cands, key=lambda x: x[0])


def build_record(p: dict) -> dict | None:
    title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
    if any(kw.lower() in title.lower() for kw in EXCLUDE_KEYWORDS):
        return None
    picked = pick_variant(p)
    if not picked:
        return None
    weight, variant = picked

    body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body)
    comment = None
    m = re.search(r"カッピングコメント\s*(.*?)\s*(?:SPEC|スペック|品名)", body)
    if m:
        comment = m.group(1).strip() or None
    material = None
    m = re.search(r"原材料名\s*(\S+)", body)
    if m:
        material = m.group(1)
    is_single = "品名 シングルオリジン" in body
    is_blend = ("品名 ブレンドコーヒー" in body) or "BLEND" in title.upper()

    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"] and material:
            detected = detect_country_name(material)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, title)

    roast_hint = None
    m = ROAST_PATTERN.search(body)
    if m:
        roast_hint = m.group(0)
    roast_level = parsed["roast_level"]
    if not roast_level and roast_hint:
        rl = parse_product(roast_hint)["roast_level"]
        roast_level = rl

    available = bool(variant.get("available"))
    return {
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
        "flavor_notes": comment,
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
    with open("data_ashiyaevian.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ashiyaevian.json に出力しました")


if __name__ == "__main__":
    main()
