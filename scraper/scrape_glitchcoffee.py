# -*- coding: utf-8 -*-
"""
scrape_glitchcoffee.py

GLITCH COFFEE & ROASTERS(shop.glitchcoffee.com、旗艦店は東京都千代田区神田錦町3-16 香村ビル 1F
(神保町)。店内に焙煎機を備える自家焙煎。東京(日本橋本町・特商法表記上の所在地)・神保町・銀座・
名古屋・大阪の5店舗で11店舗未満)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、コーヒー豆の商品を対象とする。
「Original Drip-Bag 10PC」は除外。バリエーションは「100g / 豆のまま / Whole Bean」「1kg / ...」等で、
最小重量(50g・100g・150g)の価格を代表とする。商品名先頭の【NEW】は除去する。
(浅煎り中心のロースターで焙煎度の明示は商品ページにないためroast_levelはNone)
"""

import json
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GLITCH COFFEE & ROASTERS",
    "url": "https://shop.glitchcoffee.com/",
    "platform": "Shopify",
    "address": "東京都千代田区神田錦町3-16 香村ビル 1F",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

API_BASE = "https://shop.glitchcoffee.com"
PRODUCT_BASE = "https://shop.glitchcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.IGNORECASE)

# ハンドル別の分類・産地の上書き(商品名から判定できないもの)
CATEGORY_OVERRIDES = {}
ORIGIN_OVERRIDES = {}
# 商品名の語から誤判定される精選方法の上書き(ハンドル: 精選方法)
PROCESSING_OVERRIDES = {}


def to_grams(label: str) -> int | None:
    m = WEIGHT_PATTERN.search(label or "")
    if not m:
        return None
    value = float(m.group(1))
    return int(round(value * 1000)) if m.group(2).lower() == "kg" else int(round(value))


def html_text(html: str | None) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True))


def pick_offer(p: dict, body: str) -> tuple[int | None, int, bool] | None:
    """最小重量のバリエーションを代表とし、(重量g, 価格, 在庫あり)を返す。"""
    weighted = []
    for v in p["variants"]:
        w = to_grams(v.get("title") or "")
        if w:
            weighted.append((w, v))
    if not weighted:
        return None
    weight = min(w for w, _ in weighted)
    same = [v for w, v in weighted if w == weight]
    available = any(v.get("available") for v in same)
    return weight, int(float(same[0]["price"])), available


def extra_origin(p: dict, body: str) -> str | None:
    """商品名から産地を判定できない場合の追加判定(店舗ごとに上書きする)。"""
    return None


def include_product(p: dict) -> bool:
    t = p["title"]
    if re.search(r"(Drip-?Bag|ドリップバッグ|セット|Set\b)", t, re.IGNORECASE):
        return False
    return p.get("product_type") in ("コーヒー", "Coffee", "") and any(
        to_grams(v.get("title") or "") for v in p["variants"])


def make_name(p: dict) -> str:
    name = re.sub(r"^【(?:NEW|New)】\s*", "", p["title"])
    return re.sub(r"\s+", " ", name.replace("&quot;", '"')).strip()


def detect_roast(name: str, p: dict, body: str) -> str | None:
    return None


def product_url(p: dict) -> str:
    return f"{PRODUCT_BASE}/products/{p['handle']}"



def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(f"{API_BASE}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        batch = resp.json().get("products", [])
        if not batch:
            break
        products += batch
        if len(batch) < 250:
            break
        page += 1
    return products


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        if not include_product(p):
            continue
        name = make_name(p)
        body = html_text(p.get("body_html"))
        offer = pick_offer(p, body)
        if offer is None:
            continue
        weight, price, available = offer

        handle = p["handle"]
        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        category = CATEGORY_OVERRIDES.get(handle)
        if category:
            parsed["category"] = category
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["origin_country"]:
                extra = extra_origin(p, body)
                if extra:
                    parsed["origin_country"] = extra
                    parsed["origin_source"] = "description"
            if handle in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[handle]
                parsed["origin_source"] = "raw_name"

        if handle in PROCESSING_OVERRIDES:
            parsed["processing_method"] = PROCESSING_OVERRIDES[handle]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": detect_roast(name, p, body) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": body[:400] or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": product_url(p),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_glitchcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_glitchcoffee.json に出力しました")


if __name__ == "__main__":
    main()
