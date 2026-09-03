# -*- coding: utf-8 -*-
"""
scrape_k2cafe.py

珈琲ハウスK2(k2cafe.tokyo、東京都江戸川区平井、注文後の店内焙煎・
全国送料無料)の商品情報を取得する。おちゃのこネット(Ocnk)の新しい
クリーンURLテーマ(/product-list/N・/product/N、米本珈琲・コンパス
コーヒーと同じ系統)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみDisallow: /(AI学習クローラー対策)。User-agent: *の
明示的な制限は無く、本スクレイパーの識別可能なUser-Agentは対象外。

【対象カテゴリについて】
実データ確認済み: 「自家焙煎レギュラーコーヒー」(/product-list/1、23件)・
「自家焙煎ドリップコーヒー」(2)・「水出しコーヒー」(3)の3カテゴリがあり、
「自家焙煎レギュラーコーヒー」のみがコーヒー豆単品(重量は商品名に
「200g」等の形で含まれる)。他2カテゴリはドリップバッグ・水出し用の
加工品のためスコープ外。

【重量について】
実データ確認済み: 商品詳細ページに重量選択等の`<select>`は無く、
商品名自体に重量(100g/200g)が含まれる固定商品。WEIGHT_PATTERNで
商品名から抽出する。

【在庫について】
実データ確認済み: 一覧ページの`<li>`要素に売り切れ商品は
"list_item_soldout"というclassが付与される。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "珈琲ハウスK2",
    "url": "https://www.k2cafe.tokyo/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "東京都江戸川区平井3丁目",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot/Bytespider/TikTokSpider/"
                          "meta-externalagentのみDisallow: /。User-agent: *の"
                          "明示的な制限は無く、本スクレイパーは対象外)",
}

BASE_URL = "https://www.k2cafe.tokyo"
CATEGORY_URL = f"{BASE_URL}/product-list/1"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def build_record(product_url: str, title: str, price: int | None, structural_out_of_stock: bool) -> dict:
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

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


def parse_product_detail(url: str, fallback_title: str = "", structural_out_of_stock: bool = False) -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("h1.detail_page_title, h1")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    price_el = soup.select_one("#pricech")
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    return build_record(url, title, price, structural_out_of_stock)


def scrape_category_list() -> list[dict]:
    soup = fetch_page(CATEGORY_URL)
    results = []
    for item in soup.select("li.list_item_cell"):
        link_el = item.select_one("a.item_data_link")
        title_el = item.select_one("span.goods_name")
        if not link_el or not title_el:
            continue
        results.append({
            "raw_name": title_el.get_text(strip=True),
            "product_url": link_el.get("href", ""),
            "structural_out_of_stock": "list_item_soldout" in item.get("class", []),
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"], item["raw_name"], item["structural_out_of_stock"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = parse_product_detail(url)
        print(result)
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        import json
        with open("data_k2cafe.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_k2cafe.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
