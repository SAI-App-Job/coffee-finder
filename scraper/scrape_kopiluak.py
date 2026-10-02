# -*- coding: utf-8 -*-
"""
scrape_kopiluak.py

珈琲豆専門店Kopi Luak(kopiluak2012.com、埼玉県草加市、注文ごとの自家焙煎・
約30種類の生豆)の商品情報を取得する。Wix(Wix Stores)。

【店舗発見の経緯】
2026-09-04の別セッションで「Wixサイトの商品データ埋め込みが部分的で確実な
自動抽出に時間を要する」として見送られていたが、全国再調査(埼玉県)で再検証し、
`/store-products-sitemap.xml`から全商品ページURLを列挙し、各商品ページの
JSON-LD(schema.org Product)から名前・説明・価格・在庫を取得できることを
確認して実装した。

【対象商品について】
実データ確認済み(2026-10時点): サイトマップ掲載26ページ。重複ページ
(「マンデリントバコ」の別URL、「…の複製」と付いたコピーページ)は商品名での
重複排除を行う。JSON-LDのpriceは商品ページの既定オプション(150g)の価格。
商品ページには「表示重量は焼き上がりの重さ」との注記がある。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆専門店 Kopi Luak",
    "url": "https://www.kopiluak2012.com/",
    "platform": "Wix(Wix Stores)",
    "address": "埼玉県草加市中央2-2-7",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

SITEMAP_URL = "https://www.kopiluak2012.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def normalize_name(name: str) -> str:
    return re.sub(r"[\s　]+", " ", name).strip()


def build_record(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    try:
        ld = json.loads(ld_m.group(1))
    except json.JSONDecodeError:
        return None
    if ld.get("@type") != "Product":
        return None

    name = normalize_name(ld.get("name", ""))
    desc = html.unescape(ld.get("description") or "")
    desc = re.sub(r"\s+", " ", desc).strip() or None
    offer = ld.get("offers") or {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name.replace("ガテマラ", "グアテマラ"))
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

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
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 150,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    sitemap = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=30).text
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", sitemap) if "product-page" in u]

    records = []
    seen_names = set()
    for url in urls:
        try:
            record = build_record(url)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {url} ({e})")
            continue
        if record is None:
            continue
        key = re.sub(r"[\s・\-]", "", record["raw_name"])
        if key in seen_names:
            continue
        seen_names.add(key)
        records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kopiluak.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kopiluak.json に出力しました")


if __name__ == "__main__":
    main()
