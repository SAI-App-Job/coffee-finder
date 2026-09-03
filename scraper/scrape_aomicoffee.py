# -*- coding: utf-8 -*-
"""
scrape_aomicoffee.py

青海珈琲(aomi-coffee.com、本店:東京都江東区青海、神田店・九段下店・
池袋店・神保町店・飯田橋店・TOC有明店の計7店舗を展開)の商品情報を
取得する。MakeShop。オンライン注文は全店舗共通のこのショップから
一元的に行われる。7店舗という規模はこのプロジェクトの「11店舗以上の
チェーンは対象外」という基準には該当しないため対象内(独立系自家焙煎
専門店として扱う)。

robots.txt確認済み(2026-09時点): robots.txt自体が存在せず(404、
MakeShopのシステム404ページへリダイレクト)、実質制限なし。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆」(/view/category/ct2、2ページ・51件)を
対象とする。「ブレンド」「スペシャルティコーヒー」「カフェインレス・
デカフェ」は「コーヒー豆」の横断的なサブカテゴリ(重複表示)と見られる
ため対象外。「ドリップバッグ」「コーヒーギフト」「コーヒー器具」
「スイーツ・紅茶・ハーブティー」は別カテゴリのため対象外。
「コーヒー豆」カテゴリ内にも「スペシャルティお楽しみセット」等の
複数銘柄セット商品が3件含まれるためNON_BEAN_KEYWORDSで除外する。

【重量について】
実データ確認済み: 商品詳細ページに「種類(豆/粉)」「グラム数(200g〜
1000g)」の2つの選択式`<select>`があり、価格はJSでの選択後に動的更新
される(静的HTMLには選択前のデフォルト価格のみ)。グラム数選択肢は
どの商品も先頭(プレースホルダー除く)が常に200gであることを実データで
複数商品確認済みのため、表示されているデフォルト価格を200gの価格として
扱う。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "青海珈琲",
    "url": "https://aomi-coffee.com/",
    "platform": "MakeShop",
    "address": "東京都江東区青海(本店)",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず"
                          "MakeShopのシステム404ページへリダイレクトされる、実質制限なし)",
}

BASE_URL = "https://aomi-coffee.com"
CATEGORY_PAGES = [f"{BASE_URL}/view/category/ct2", f"{BASE_URL}/view/category/ct2?page=2"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_from_select(soup: BeautifulSoup) -> int | None:
    for select_el in soup.select('select[data-id="makeshop-item-option2"]'):
        for option in select_el.select("option"):
            value = option.get("value", "")
            if not value or value == "0":
                continue
            m = WEIGHT_PATTERN.search(option.get_text())
            if m:
                return int(m.group(1))
    return None


def build_record(product_url: str, title: str, price: int | None, weight_g: int | None) -> dict | None:
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, fallback_title: str = "") -> dict | None:
    soup = fetch_page(url)
    title_el = soup.select_one("h1.item-name")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    price_el = soup.select_one('[data-id="makeshop-item-price:1"]')
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    weight_g = parse_weight_from_select(soup)

    return build_record(url, title, price, weight_g)


def scrape_category_list(url: str) -> list[dict]:
    soup = fetch_page(url)
    results = []
    for link_el in soup.select("p.item-list-name a[href]"):
        product_url = link_el.get("href", "")
        if product_url.startswith("/"):
            product_url = BASE_URL + product_url
        product_url = product_url.split("?")[0]
        results.append({"raw_name": link_el.get_text(strip=True), "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cat_url in CATEGORY_PAGES:
        for item in scrape_category_list(cat_url):
            items_by_url.setdefault(item["product_url"], item)

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
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

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
        with open("data_aomicoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_aomicoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
