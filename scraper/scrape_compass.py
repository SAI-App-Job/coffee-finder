# -*- coding: utf-8 -*-
"""
scrape_compass.py

コンパスコーヒー(compass-coffee.com、東京都品川区旗の台、複数店舗展開の
自家焙煎専門店)の商品情報を取得する。おちゃのこネット(Ocnk)の新しい
クリーンURLテーマ(/product-list/N・/product/N、米本珈琲と同じURL方式だが
一覧ページのリンクにitem_data_link等の専用classが無く`<a href="/product/N">`
のみで示される点が異なる、DOM構造の異なるテーマバリエーション)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみDisallow: /(AI学習クローラー対策)。User-agent: *の
明示的な制限は無く、本スクレイパーの識別可能なUser-Agentは対象外。

【対象カテゴリについて】
実データ確認済み: トップページの地域別バナーが指す6カテゴリ(1=オリジナル
ブレンド・2=アフリカ・3=中南米・5=大洋州・6=アジア/オセアニア・
15=南米)+9=デカフェの計7カテゴリ、全24件がすべてコーヒー豆単品
(ブレンド・ストレート・デカフェ)で非コーヒー豆商品は無い。ギフト
おすすめ("/product-group/6")は別URL方式のグループページのため対象外。

【重量・焙煎度が選択式である点について】
実データ確認済み: 商品詳細ページに重量選択(200g〜600g等、商品により
異なる)・焙煎度選択(シナモン〜イタリアンの7段階)の2つの`<select>`が
あり、価格は重量のみで決まる(実データ確認済み、pConf.priceArray内の
同一重量IDでは焙煎度・挽き方に関わらず同額)。ページ内の#pricechが
「1,800円～5,400円」のような価格帯表示のため、最初の数値(最小重量の
価格)を採用する。重量は最初の`<select>`(重量選択)の先頭の実オプション
(プレースホルダー「選択してください」を除く)から抽出する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "コンパスコーヒー",
    "url": "https://www.compass-coffee.com/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "東京都品川区旗の台",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot/Bytespider/TikTokSpider/"
                          "meta-externalagentのみDisallow: /。User-agent: *の"
                          "明示的な制限は無く、本スクレイパーは対象外)",
}

BASE_URL = "https://www.compass-coffee.com"
LIST_CATEGORIES = {
    "1": "オリジナルブレンド",
    "2": "アフリカ",
    "3": "中南米",
    "5": "大洋州",
    "6": "アジア",
    "9": "デカフェ",
    "15": "南米",
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


def parse_weight_from_select(soup: BeautifulSoup) -> int | None:
    select_el = soup.select_one("select")
    if not select_el:
        return None
    for option in select_el.select("option"):
        value = option.get("value", "")
        if not value:
            continue
        m = WEIGHT_PATTERN.search(option.get_text())
        if m:
            return int(m.group(1))
    return None


def build_record(product_url: str, title: str, price: int | None, weight_g: int | None,
                  roast_selectable: bool) -> dict:
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

    stock_status = detect_stock_status(title)

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
        "roast_selectable": roast_selectable,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, fallback_title: str = "") -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("h1.detail_page_title, h1")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    price_el = soup.select_one("#pricech")
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    weight_g = parse_weight_from_select(soup)
    if weight_g is None:
        m = WEIGHT_PATTERN.search(title)
        weight_g = int(m.group(1)) if m else None

    roast_selectable = len(soup.select("select")) >= 2

    return build_record(url, title, price, weight_g, roast_selectable)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/product-list/{cid}")
    results = []
    for item in soup.select("li.list_item_cell"):
        link_el = item.select_one('a[href*="/product/"]')
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
    for cid in LIST_CATEGORIES:
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], item)
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
            detail = parse_product_detail(product_url, item["raw_name"])
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
        with open("data_compass.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_compass.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
