# -*- coding: utf-8 -*-
"""
scrape_migliorecoffee.py

MIGLIORE COFFEE(ミリオーレコーヒー、山口県防府市華園町13-41 まるき華城店敷地内)の商品情報を取得する。
Shopify。

【対象商品について】
実データ確認済み(2026-10-15): Shopifyの`/products.json`のうち product_type が「コーヒー豆」の2商品
(東ティモール ロビボ集落、ブラジル カペベ農協)。バリエーションは「150g / 豆のまま」「150g / 挽いたもの」
「300g / ...」「10g / ドリップパック(バッグ)」。最小重量の豆(150g、豆のまま)の価格を代表にする。
ドリップパック・ドリップバッグのバリエーションは除外。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "MIGLIORE COFFEE",
    "url": "https://migliorecoffee.com/",
    "platform": "Shopify",
    "address": "山口県防府市華園町13-41 まるき華城店敷地内",
    "prefecture": "山口県",
    "robots_txt_status": "未確認(Shopify標準構成。公開の/products.jsonを使用)",
    "source_note": "公式サイト(https://migliorecoffee.com/)のShopify商品データ(/products.json)と特定商取引法に基づく表記(/policies/terms-of-service)を2026-10-15に確認",
    "last_verified_at": "2026-10-15",
}

BASE_URL = "https://migliorecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"ロースト[:：]\s*([^\s（(]+)\s*[（(]([^）)]+)[）)]")
PROCESS_PATTERN = re.compile(r"精製[:：]\s*(\S+)")
COUNTRY_TAGS = {"東ティモール": "東ティモール", "ブラジル": "ブラジル"}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"[\s　]+", " ", p["title"]).strip()

        # 豆のまま/挽いたもののみ(ドリップパック・バッグは除外)
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "ドリップ" in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), "豆のまま" in vt, v))
        if not weighted:
            continue
        min_w = min(w for w, _, _ in weighted)
        cands = [(whole, v) for w, whole, v in weighted if w == min_w]
        cands.sort(key=lambda x: not x[0])  # 豆のままを優先
        variant = cands[0][1]
        available = bool(variant.get("available"))

        body = re.sub(r"\s+", " ", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        roast_hint = None
        roast_level = None
        m = ROAST_PATTERN.search(body)
        if m:
            roast_hint = m.group(1)
            if m.group(2) == "フルシティ":
                roast_level = "フルシティロースト"
        m = PROCESS_PATTERN.search(body)
        process = m.group(1) if m else None
        if process:
            process = {"ウォッシュト": "ウォッシュド"}.get(process, process)

        parsed = parse_product(title)
        origin = parsed["origin_country"]
        if not origin:
            for t in p.get("tags") or []:
                if t in COUNTRY_TAGS:
                    origin = COUNTRY_TAGS[t]
                    break
        farm = "カペベ農協" if "カペベ農協" in title else None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "ストレート",
            "origin_country": origin,
            "origin_source": parsed["origin_source"] or "shop_tag",
            "designated_brand": parsed["designated_brand"],
            "processing_method": process or parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_hint,
            "flavor_notes": body[:400] or None,
            "farm_note": farm,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": min_w,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{urllib.parse.quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_migliorecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_migliorecoffee.json に出力しました")


if __name__ == "__main__":
    main()
