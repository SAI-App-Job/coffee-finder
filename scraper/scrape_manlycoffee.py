# -*- coding: utf-8 -*-
"""
scrape_manlycoffee.py

MANLY COFFEE(https://manly-coffee.com/、福岡県福岡市中央区平尾2-14-21)の商品情報を取得する。Shopify。

【店舗の実在・自家焙煎】
公式サイトAccess(/pages/map)に「〒810-0014 福岡県福岡市中央区平尾2丁目14-21」「OPEN 10:00-17:00
定休日 月曜日 火曜日」、About(/pages/about)に「2016年9月 平尾にリニューアルオープン」
「2022年春 念願の焙煎器 Loring Smart Roaster...ROASTERYとしてうまれかわり」とある(2026-10-20確認)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「飲料」(コーヒー豆)の商品と、
タイトルにMILK CHOCOLATE(ブレンド)を含む豆商品を対象とする。「大袋」(1kg以上のみ)、セット、ギフト、
ドリップ・コーヒーバッグ、ミルクブリュー、器具は除外。バリエーションは「<挽き方> / <重量>」の組のうち
「豆のまま」(挽き方の記載がないものも含む)で、100gがあれば100g、無ければ最小重量(ゲイシャの50g等)を代表とする。
在庫は代表バリエーションのavailableを反映する(売切れ・残りわずか表記が多数)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "MANLY COFFEE",
    "url": "https://manly-coffee.com/",
    "platform": "Shopify",
    "address": "福岡県福岡市中央区平尾2丁目14-21",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(Shopify標準。/products.jsonは禁止対象外。2026-10-20確認)",
    "source_note": "公式サイトのAccess(/pages/map)・About(/pages/about)と/products.jsonを2026-10-20に確認。住所は公式Accessページの記載(番地まで)。焙煎機Loring Smart Roaster設置のROASTERY",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://manly-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*([gｇkKｋ])")
EXCLUDE_TITLE = ("セット", "ギフト", "大袋", "ミルクブリュー", "MILK BREW", "Coffee Bags", "コーヒーバッグ")


def is_bean_product(p: dict) -> bool:
    title = p["title"]
    if any(k in title for k in EXCLUDE_TITLE):
        return False
    if p.get("product_type") == "飲料":
        return True
    return "MILK CHOCOLATE" in title and any("豆のまま" in v["title"] for v in p["variants"])


def clean_title(title: str) -> str:
    title = re.sub(r"【[^】]*】", "", title)  # 【 NEW！】【 残りわずか 】【 SOLD OUT 】等
    return re.sub(r"\s+", " ", title).strip()


def pick_variant(p: dict):
    candidates = []
    for v in p["variants"]:
        vt = v.get("title") or ""
        if "挽" in vt:
            continue
        m = WEIGHT_PATTERN.search(vt)
        if not m:
            continue
        w = int(m.group(1)) * (1000 if m.group(2) in "kKｋ" else 1)
        if w >= 1000:
            continue
        candidates.append((w, v))
    if not candidates:
        return None
    for w, v in candidates:
        if w == 100:
            return w, v
    return min(candidates, key=lambda x: x[0])


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if not is_bean_product(p):
            continue
        picked = pick_variant(p)
        if picked is None:
            continue
        weight, variant = picked
        title = clean_title(p["title"])
        is_milk_choc = "MILK CHOCOLATE" in title

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if is_milk_choc:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["roast_level"] = "中深煎り"
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            if not detected and "ネパール" in title:  # 国名辞書に無い産地を明示
                parsed["origin_country"] = "ネパール"
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            # 「ドン ハイメ」の「ハイ」を焙煎度と誤検出するため、タイトルに焙煎度の明記が無ければ不明とする
            if not re.search(r"煎り|ロースト|Roast", title, re.I):
                parsed["roast_level"] = None

        available = bool(variant.get("available"))
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
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
    with open("data_manlycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_manlycoffee.json に出力しました")


if __name__ == "__main__":
    main()
