# -*- coding: utf-8 -*-
"""
scrape_koyamacoofi.py

こやまこおふぃ(koyamacoofi.theshop.jp、〒800-0025 福岡県北九州市門司区
柳町1-5-25、直火焙煎の自家焙煎豆専門店)の商品情報を取得する。
THE SHOP(BASE系)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・珈琲家あのころ等と同一の
記述(curl/python-requests等の一般的なHTTPクライアントは個別にDisallow:
/指定があるが、User-agent: *ルールでは/cart/・/shops/・違反報告ページ
以外はAllow: /)。本スクレイパーが使う商品詳細ページ(/items/)と
カテゴリ一覧ページ(/categories/)はいずれもDisallow対象に含まれない。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「フィルター」(id=205632、非対象)・
「ストレート豆」(id=205361、12件)・「ブレンド豆」(id=205626)の3
カテゴリがあり、珈琲家あのころのような両者を包含する親カテゴリが
無いため、ストレート豆・ブレンド豆の2カテゴリを個別に巡回する。

【商品詳細ページのJSON-LDについて】
実データ確認済み: descriptionは「生産地：」等のラベル付き構造化
テキストではなく自由記述のマーケティング文のみ(珈琲家あのころ/NAGI
COFFEEとは異なる)。ただし商品名(例:「ハイマウンテン（100g）」
「温泉ブルボン エルサルバドル（100g）」)にcoffee_parser.pyの
REGION_TO_COUNTRY(ハイマウンテン→ジャマイカ、キリマンジャロ→タンザニア
等)で産地判定可能な地域名・国名が含まれるため、商品名解析のみで
十分な精度が得られる(実データ確認済み、全24件中「セレソン」
「ピーベリークラシコ」の2件のみ産地不明)。

【重量について】
実データ確認済み: 全商品が「（100g）」の単一重量のみ(全24件で確認済み、
重量違いバリアントは無い)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "こやまこおふぃ",
    "url": "https://koyamacoofi.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "福岡県北九州市門司区柳町1-5-25",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・珈琲家あのころと同一の記述。"
                          "/cart/・/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://koyamacoofi.theshop.jp"
CATEGORY_IDS = ["205361", "205626"]  # ストレート豆・ブレンド豆(理由はモジュールdocstring参照)
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def build_record(product_url: str, product: dict) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product)


def scrape_category_list(category_id: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{category_id}")
    results = []
    seen_urls = set()
    for link_el in soup.select('a[href*="/items/"]'):
        title_el = link_el.select_one('[class*="itemTitleText"]')
        if not title_el:
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = []
    seen_urls = set()
    for category_id in CATEGORY_IDS:
        for item in scrape_category_list(category_id):
            if item["product_url"] not in seen_urls:
                seen_urls.add(item["product_url"])
                items.append(item)

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        try:
            detail = parse_product_detail(item["product_url"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_koyamacoofi.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_koyamacoofi.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
