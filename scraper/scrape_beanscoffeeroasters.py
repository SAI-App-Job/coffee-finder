# -*- coding: utf-8 -*-
"""
scrape_beanscoffeeroasters.py

Beans. Coffee&Roasters(beanscoffee.jp、株式会社SSC、神戸六甲道店・神戸元町店の2店舗)の
商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10-20時点): Shopifyの`/products.json`(全36件)のうち、tagsに
「beans」を持ち、ドリップバッグ・定期便・テイスティングセット(15g×5)・お試しサイズ(15g)
を除いた8件(単一産地6件、デカフェ1件、ブレンド1件)を対象とする。バリエーションは
「豆のまま」「粉(中挽き)」「粉(水出し用)」で、「豆のまま(おすすめ)」の100g価格を採用する。
"""

import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Beans. Coffee&Roasters",
    "url": "https://beanscoffee.jp/",
    "platform": "Shopify",
    "address": "兵庫県神戸市灘区高徳町3丁目1-7-103",
    "prefecture": "兵庫県",
    "robots_txt_status": "確認済み(2026-10-20): User-agent: * で Allow: /。/cart/・/checkout等のみDisallow。商品ページ・/products.jsonは対象外",
    "source_note": "https://beanscoffee.jp/products.json(2026-10-20取得、Shopify自社EC)。店舗情報 https://beanscoffee.jp/pages/店舗情報 で神戸六甲道店(灘区高徳町3丁目1-7-103、一号店・会社本店所在地と同一)と神戸元町店(中央区元町通1丁目9-5)の2店舗を確認。トップページに「神戸元町で自家焙煎したスペシャルティコーヒー」の記述。住所は一号店の六甲道店を採用。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://beanscoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_TAGS = {"dripbag", "試飲", "GIFT", "latte"}
EXCLUDE_TITLE = ("定期便", "テイスティングセット", "お試しサイズ", "ドリップバッグ", "スターターセット")
FLAVOR_RE = re.compile(r"フレーバー\s*-\s*FLAVOR\s*-\s*(.+?)(?:\s*※|\s*ストーリー|$)")
ROAST_RE = re.compile(r"焙煎度\s*-\s*ROAST\s*-\s*(\S+)")
ROAST_JA = {"Light": "浅煎り", "Medium": "中煎り", "Medium-Dark": "中深煎り", "Dark": "深煎り",
            "浅煎り": "浅煎り", "中煎り": "中煎り", "中深煎り": "中深煎り", "深煎り": "深煎り"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        tags = set(p.get("tags") or [])
        if "beans" not in tags or tags & EXCLUDE_TAGS:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k in title for k in EXCLUDE_TITLE):
            continue

        whole = None
        for v in p["variants"]:
            if (v.get("title") or "").startswith("豆のまま") and v.get("grams"):
                whole = v
                break
        if not whole:
            continue

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        fm = FLAVOR_RE.search(body)
        flavor = fm.group(1).strip() if fm else None
        rm = ROAST_RE.search(body)
        roast_raw = rm.group(1) if rm else None

        parsed = parse_product(title)
        is_blend = "Blend" in title or "ブレンド" in title
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            bm = re.search(r"FLAVOR\s*[：:]\s*(.+?)\s*※", body)
            desc = ("インドネシア(深煎り)・グアテマラ(中深煎り)・ブラジル(中煎り)の3種構成。" + (bm.group(1) if bm else "")).strip()
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            desc = flavor
        if not parsed.get("roast_level") and roast_raw in ROAST_JA:
            parsed["roast_level"] = ROAST_JA[roast_raw]

        available = bool(whole.get("available"))
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
            "price": int(float(whole["price"])),
            "weight_g": int(whole["grams"]),
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beanscoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beanscoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
