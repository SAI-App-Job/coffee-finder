# -*- coding: utf-8 -*-
"""
scrape_yurafulcoffee.py

自家焙煎珈琲ゆらふる(yuraful-coffee.com、茨城県那珂市竹ノ内2-2-6)の商品情報を取得する。Wix Stores。
(旧BASE yuraful.base.ec は準備中のため使わない。)

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml に商品ページ(/product-page/<slug>)が23件。
各ページのJSON-LD(Product)から name / description / offers.price / availability を取得する。
商品名の末尾に重量(200g)が入っており、価格は200gの1個価格(税込表示)。
【除外】スペシャルセット/ミックスセット/ゆらふるブレンド10個入り(ドリップバッグ系の10個入り)、
カフェオレベース、リキッドコーヒー(液体商品)。結果として豆は17銘柄(200g)。
【description】「商品の詳細を入力してください…」はWixの未編集テンプレート文のため捨てる。
"""

import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲ゆらふる",
    "url": "https://www.yuraful-coffee.com/",
    "platform": "Wix",
    "address": "茨城県那珂市竹ノ内2-2-6",
    "prefecture": "茨城県",
    "robots_txt_status": "許可(2026-10確認。User-agent: * は Allow: /。商品ページは制限対象外)",
}

SITEMAP_URL = "https://www.yuraful-coffee.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["個入り", "セット", "カフェオレベース", "リキッドコーヒー", "ドリップ", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|深煎り|中浅煎り|浅煎り|中煎り)")
PLACEHOLDER = "商品の詳細を入力してください"


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
        title = re.sub(r"\s+", " ", (ld.get("name") or "").replace("　", " ")).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        wm = WEIGHT_PATTERN.search(title)
        weight = int(wm.group(1)) if wm else None
        if weight is None:
            continue

        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        price = int(float(offer["price"])) if offer.get("price") not in (None, "") else None
        available = "OutOfStock" not in (offer.get("availability") or "")

        desc = (ld.get("description") or "").replace("&#010;", " ").replace("&#10;", " ")
        desc = re.sub(r"\s+", " ", desc).strip()
        if desc.startswith(PLACEHOLDER):
            desc = ""
        desc = desc[:400] or None

        roast_hint = ROAST_PATTERN.search(desc or "")
        parsed = parse_product(title + (" " + roast_hint.group(1) if roast_hint else ""))
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
            "roast_level": parsed["roast_level"] or (roast_hint.group(1) if roast_hint else None),
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
    with open("data_yurafulcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yurafulcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
