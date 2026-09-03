# -*- coding: utf-8 -*-
"""
scrape_yonemoto.py

米本珈琲(よねもとこーひー、yonemoto-coffee.com、東京都中央区築地、1960年創業)の
商品情報を取得する。おちゃのこネット(Ocnk)だが、Denim bis・幸音珈琲で見た
「?product_id=N」形式ではなく、クリーンURL(/product-list/N・/product/N)の
新しいテーマを使用している。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみDisallow: /(AI学習クローラー対策)。User-agent: *の
明示的な制限は無く、本スクレイパーの識別可能なUser-Agentは対象外。

【対象カテゴリについて】
実データ確認済み: 「ブレンド」(/product-list/2、6件)・「ストレート」
(/product-list/3、11件)・「デカフェ」(/product-list/7、1件)の3カテゴリが
コーヒー豆単品を指す。「グッズ・その他」(4)・「生豆」(5、未焙煎豆)・
「コーヒー豆セット」(6、アソート)・「ドリップバッグ」(8)・「ギフト」(9)は
対象外。

【重量について】
実データ確認済み: 商品詳細ページの「重み」ラベル(delivery_option)に
「200g」のように明記されている。商品名自体には重量が含まれない
(「ジョン・レノン愛飲！シティーブレンド」等)。

【在庫について】
実データ確認済み: 一覧・詳細ページのどちらにも構造化された品切れ表示要素が
見当たらないため、商品名のテキストのみで在庫状態を判定する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "米本珈琲",
    "url": "https://www.yonemoto-coffee.com/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "東京都中央区築地",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot/Bytespider/TikTokSpider/"
                          "meta-externalagentのみDisallow: /。User-agent: *の"
                          "明示的な制限は無く、本スクレイパーは対象外)",
}

BASE_URL = "https://www.yonemoto-coffee.com"
# 理由はモジュールdocstring参照(コーヒー豆単品を指す3カテゴリ)
LIST_CATEGORIES = {
    "2": "ブレンド",
    "3": "ストレート",
    "7": "デカフェ",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_from_delivery_option(soup: BeautifulSoup) -> int | None:
    for p in soup.select("p.delivery_option"):
        m = WEIGHT_PATTERN.search(p.get_text())
        if m:
            return int(m.group(1))
    return None


def build_record(product_url: str, title: str, price: int | None, weight_g: int | None,
                  category_hint: str) -> dict:
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

    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
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


def parse_product_detail(url: str, fallback_title: str = "", category_hint: str = "") -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    price_el = soup.select_one("#pricech")
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    weight_g = parse_weight_from_delivery_option(soup)
    if weight_g is None:
        m = WEIGHT_PATTERN.search(title)
        weight_g = int(m.group(1)) if m else None

    return build_record(url, title, price, weight_g, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/product-list/{cid}")
    results = []
    for item in soup.select("li.list_item_cell"):
        link_el = item.select_one("a.item_data_link")
        title_el = item.select_one("span.goods_name")
        if not link_el or not title_el:
            continue
        results.append({
            "raw_name": title_el.get_text(strip=True),
            "product_url": link_el.get("href", ""),
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["raw_name"], item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

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
        with open("data_yonemoto.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_yonemoto.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
