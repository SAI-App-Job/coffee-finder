# -*- coding: utf-8 -*-
"""
scrape_mameraku.py

自家焙煎珈琲 豆楽(まめらく、mameraku.jp、愛知県日進市浅田平子2丁目187)のオンライン
ショップの商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(81件)のうちproduct_typeが
Straight / Blend / Decaf / Espresso の焙煎豆商品のみを対象とする。
ポストカード(写真)・ペーパーフィルター・3種飲み比べセット・ギフトBOX・水出し珈琲パックは除外。
同一銘柄が「200g」「500g」の別商品として並ぶため、最小重量(200g)の商品を代表とする
(秋季限定ブレンドなど500gと200gの両方がある商品も同様)。重量は商品名末尾の「200g」表記による。
焙煎度は商品名の「深煎り」「浅煎り」、なければ説明文の「深煎り。」等の記載から取得する。
エスプレッソ(クラシック・エスターテ等)はブレンドとして収録する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲 豆楽",
    "url": "https://mameraku.jp/",
    "platform": "Shopify",
    "address": "愛知県日進市浅田平子2丁目187",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://mameraku.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = ("Straight", "Blend", "Decaf", "Espresso")
WEIGHT_IN_TITLE = re.compile(r"(\d+)\s*[gｇ]\s*$")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_WORDS = ("セット", "ギフト", "水出し", "ペーパー")


def clean_name(title: str) -> str:
    t = title.replace("　", " ")
    m = re.search(r"『([^』]+)』", t)
    if m:  # 秋季限定商品: 「【秋季限定商品】 11/24までの期間限定 『夜長 -YoNaGa-』 500g」
        t = m.group(1) + " " + (WEIGHT_IN_TITLE.search(t).group(0) if WEIGHT_IN_TITLE.search(t) else "")
    return re.sub(r"\s+", " ", t).strip()


def scrape_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1

    # 銘柄名(重量除去)ごとに最小重量の商品を代表にする
    best: dict[str, tuple[int, dict, str]] = {}
    for p in products:
        if p.get("product_type") not in BEAN_TYPES:
            continue
        if any(w in p["title"] for w in EXCLUDE_WORDS):
            continue
        name = clean_name(p["title"])
        wm = WEIGHT_IN_TITLE.search(name)
        if not wm:
            continue
        weight = int(wm.group(1))
        base = WEIGHT_IN_TITLE.sub("", name).strip()
        if base not in best or weight < best[base][0]:
            best[base] = (weight, p, base)

    records = []
    for base, (weight, p, name) in best.items():
        variants = p["variants"]
        available = any(v.get("available") for v in variants)
        price = int(float(min(variants, key=lambda v: float(v["price"]))["price"]))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        desc_lines = [ln for ln in body.split("\n") if ln and not ln.startswith(("エスプレッソブレンドは", "挽き売り"))]
        desc = re.sub(r"\s+", " ", " ".join(desc_lines))[:300] or None
        rm = ROAST_PATTERN.search(base) or ROAST_PATTERN.search(body)
        roast = rm.group(1) if rm else None
        if rm and not ROAST_PATTERN.search(base):
            rng = re.search(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)[〜~～](極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)", body)
            if rng:
                roast = rng.group(1) + "〜" + rng.group(2)

        parsed = parse_product(base)
        ptype = p["product_type"]
        if ptype in ("Blend", "Espresso") or "ブレンド" in base:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["processing_method"] = None
        else:
            parsed["category"] = "ストレート"
            detected = detect_country_name(base)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, base)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,  # parse_product由来の焙煎度は商品名中の語を誤検出し得るため使わない
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mameraku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameraku.json に出力しました")


if __name__ == "__main__":
    main()
