# -*- coding: utf-8 -*-
"""
scrape_scratchcoffee.py

SCRATCH COFFEE(scratch-coffee.net、東京都葛飾区四つ木1-33-7、2020年開業の
自家焙煎珈琲とスパイス料理のテイクアウト専門店。受注後に生豆から焙煎して発送、
シェアロースターも併設)の商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`の全7商品ページのうち、
JSON-LD(schema.org Product)の名前に「(200g)」を含む豆商品5銘柄(ホンジュラス
オーガニックカフェインレス・グァテマラ・ベトナム・マンデリン・エチオピア)を対象とする。
DIP STYLE COFFEE BAG(コーヒーバッグ)・キーホルダーは除外。サイトマップのURLスラッグ
(例: 「ブラジル-カフェインレス」)は商品名と一致しない古い値が残っているため、
商品名は必ずJSON-LDの値を使い、product_urlはサイトマップの実URLを用いる。
商品名の「(200g)※生豆時約250g」は焙煎後200g(生豆250g)の意味で、重量は200gとする。
"""

import html
import json
import re
import unicodedata
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "SCRATCH COFFEE",
    "url": "https://www.scratch-coffee.net/",
    "platform": "Wix(Wix Stores)",
    "address": "東京都葛飾区四つ木1-33-7",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.scratch-coffee.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
SIZE_PATTERN = re.compile(r"[（(]\s*(\d+)\s*g\s*[)）](?:\s*※[^\s]*)?")
ROAST_PATTERN = re.compile(r"焙煎[（(]([^）)]*煎り)[)）]")


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def build_record(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))
    full_name = re.sub(r"\s+", " ", html.unescape(ld.get("name", ""))).strip()
    size_m = SIZE_PATTERN.search(full_name)
    if not size_m or "バッグ" in full_name or "BAG" in full_name.upper():
        return None
    weight_g = int(size_m.group(1))
    name = unicodedata.normalize("NFKC", SIZE_PATTERN.sub("", full_name)).strip()

    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_m = ROAST_PATTERN.search(desc)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(name),
        "grade": parsed["grade"],
        "roast_level": roast_m.group(1) if roast_m else parsed["roast_level"],
        "roast_hint": "受注後焙煎",
        "flavor_notes": desc[:500] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            record = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_scratchcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_scratchcoffee.json に出力しました")


if __name__ == "__main__":
    main()
