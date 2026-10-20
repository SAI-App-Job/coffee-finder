# -*- coding: utf-8 -*-
"""
scrape_manucoffee.py

manucoffee(オンラインストア https://online.manucoffee.com/ 、公式 https://www.manucoffee.com/ )の商品情報を取得する。Shopify。

【登録住所について】
公式サイトのSHOP LIST(https://www.manucoffee.com/shoplist/)に、焙煎所を兼ねる「manucoffee roasters KUJIRA」
(〒810-0012 福岡市中央区白金1-18-28)、大名店(〒810-0041 福岡市中央区大名1-1-3 石井ビル1F)、春吉店
(〒810-0004 福岡市中央区渡辺通3-11-2 ボーダータワー1F。会社概要の所在地もこの住所)が掲載されている。
公式サイトに「本店」の表記は無く、大名店を本店とする根拠は確認できなかった。一方KUJIRA店は店内に
Loring Smart Roasterを置く焙煎拠点で、ブランドの旗艦店と紹介されているため、番地まで確認できる
KUJIRA店(白金1-18-28)を登録住所とした。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「COFFEE」で、
「ビーンズ(豆のまま)」バリエーションを持つ商品を対象とする(ドリップバッグ・1kgコーヒーパック・
クイックマヌ・グッズは除外)。バリエーションは「200g / ビーンズ(豆のまま)」と1kgで、1kg(事業者向け大容量)は
除外して200gを代表とする。ニカラグアCOE 1位ゲイシャのみ100g(キャニスター付)が最小。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "manucoffee",
    "url": "https://online.manucoffee.com/",
    "platform": "Shopify",
    "address": "福岡県福岡市中央区白金1-18-28 manucoffee roasters KUJIRA",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(Shopify標準。/products.jsonは禁止対象外。2026-10-20確認)",
    "source_note": "公式SHOP LIST(https://www.manucoffee.com/shoplist/)と/products.jsonを2026-10-20に確認。住所は番地まで確認できる焙煎所兼店舗のKUJIRA店。大名店(大名1-1-3)等の他店舗あり",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://online.manucoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)

# 産地がタイトルに無い商品(本文の「内容」「生産国」より確認)
ORIGIN_OVERRIDES = {"dark-roast": "ニカラグア"}
ROAST_OVERRIDES = {"dark-roast": "深煎り"}  # 「マヌコーヒー唯一の深煎り」「ダークロースト」


def clean_title(title: str) -> str:
    title = title.replace("【デカフェ】", "デカフェ ")
    title = re.sub(r"【[^】]*】", "", title)
    title = re.sub(r"[\U0001F000-\U0001FFFF☀-➿️]", "", title)
    title = re.sub(r"[（(]\s*200g\s*/\s*1kg\s*[）)]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def pick_bean_variant(p: dict):
    best = None
    for v in p["variants"]:
        vt = v.get("title") or ""
        if "ビーンズ" not in vt:
            continue
        m = WEIGHT_PATTERN.search(vt)
        if not m:
            continue
        w = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
        if w >= 1000:
            continue
        if best is None or w < best[0]:
            best = (w, v)
    return best


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != "COFFEE" or "DRIPBAG" in p["title"]:
            continue
        picked = pick_bean_variant(p)
        if picked is None:
            continue
        weight, variant = picked
        title = clean_title(p["title"])
        handle = p["handle"]

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None
        if "キャニスター付" in (variant.get("title") or ""):
            desc = "※100g(キャニスター付)の価格。" + (desc or "")

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
            if handle in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[handle]
                parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)
            if "デカフェ" in title:
                parsed["category"] = "デカフェ"
        roast = ROAST_OVERRIDES.get(handle)
        if roast is None and not re.search(r"煎り|ロースト|Roast", title, re.I):
            roast = None
        elif roast is None:
            roast = parsed["roast_level"]

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
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{handle}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_manucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_manucoffee.json に出力しました")


if __name__ == "__main__":
    main()
