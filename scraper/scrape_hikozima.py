# -*- coding: utf-8 -*-
"""
scrape_hikozima.py

自家焙煎珈琲工房 飛行島(hikozima.com、宮城県白石市福岡蔵本字西町25)の商品情報を取得する。Wix。

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml に商品ページ(/product-page/<slug>)が22件
並び、各ページのJSON-LD(Product)から name / description / offers.price / availability を取得する。
価格は「100gごとに¥740」の100g単位価格(グラム選択式)なので、ページ内の
「100gごとに」表記から基準グラム(100g)を取り、100gの価格を代表とする。
コーヒー豆以外(コーノフィルター、ドリップパック、ギフト用ドリップパック、ネコポス便の
電話・メール受付専用商品)と、200g/150gの複数個セット(飛鳥ブレンド等)は除外する。
"""

import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲工房 飛行島",
    "url": "https://www.hikozima.com/",
    "platform": "Wix",
    "address": "宮城県白石市福岡蔵本字西町25",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Wix標準構成)",
}

SITEMAP_URL = "https://www.hikozima.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["フィルター", "ドリップパック", "ネコポス", "個入り", "ギフト"]


def fetch(url: str) -> str:
    resp = requests.get(quote(url, safe=":/?=&#%"), headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_product_ld(html: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def scrape_all_products() -> list[dict]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", sitemap)

    records = []
    for url in urls:
        time.sleep(CRAWL_DELAY_SECONDS)
        html = fetch(url)
        ld = extract_product_ld(html)
        if not ld:
            continue
        title = re.sub(r"\s+", " ", ld.get("name") or "").strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        price = int(float(offer["price"])) if offer.get("price") not in (None, "") else None
        available = "OutOfStock" not in (offer.get("availability") or "")

        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        wm = re.search(r"(\d+)\s*g[（(]グラム[）)]|(\d+)\s*gごとに", text)
        weight = int(next(g for g in wm.groups() if g)) if wm else None

        desc = re.sub(r"\s+", " ", ld.get("description") or "").strip()[:400] or None

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
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": offer.get("url") or url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hikozima.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hikozima.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
