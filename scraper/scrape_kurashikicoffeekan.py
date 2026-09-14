# -*- coding: utf-8 -*-
"""
scrape_kurashikicoffeekan.py

倉敷珈琲館(kura-coffee.shop-pro.jp、〒710-0054 岡山県倉敷市本町4-1、
倉敷美観地区の自家焙煎珈琲専門店)の商品情報を取得する。カラーミー
ショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://kura-coffee.shop-pro.jp/?mode=sk)の「販売
業者」欄には運営会社(穴吹エンタープライズ株式会社)の香川県高松市の
登記住所が記載されているが、実店舗(倉敷美観地区)の所在地は公式サイト
(https://www.kurashiki-coffeekan.com/)で候補リストと一致する
「〒710-0054 岡山県倉敷市本町4-1」であることを確認した(2026-09時点)。
本プロジェクトでは実際の店舗所在地を採用する(東珈琲店/ONSAYA COFFEEと
同種のケース)。

robots.txt確認済み(2026-09時点): shop-pro.jp標準のrobots.txtで、本
スクレイパーが使う商品一覧・詳細ページ(?mode=cate, ?pid=)は制限対象外。

【対象カテゴリについて】
実データ確認済み: 商品カテゴリは「珈琲豆(cbid=2471964、12件)」
「ドリップパック(cbid=2471965)」「オリジナル商品(cbid=2471969)」
「ネル(cbid=2471970、ネルドリップ用フィルター)」「ギフト(cbid=2471971)」
「お試しセット(cbid=2705348)」「【珈琲豆の定期購入】(cbid=2986152)」の
7種類。珈琲豆カテゴリのみを対象とする(その他はドリップパック・器具・
ギフト・詰め合わせ・定期購入で単一銘柄のコーヒー豆販売ではないため
非対象と判断)。

【商品情報の取得方法について】
実データ確認済み: 珈琲豆カテゴリの一覧ページ(li.product-list__unit)に
商品名(a.product-list__name)・価格(span.product-list__price、税込)が
静的HTMLで直接出力されている。重量は商品名に含まれていない(全12件で
確認済み、店舗の基準重量は不明のためweight_gはnullとする)。

【在庫状況について】
実データ確認済み: 売り切れ商品は価格の代わりにspan.product-list__soldout
(テキスト"SOLD OUT")が表示される(全12件中「マンデリン」の1件のみ該当)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "倉敷珈琲館",
    "url": "https://kura-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "岡山県倉敷市本町4-1",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、本スクレイパーが"
                          "使う商品一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://kura-coffee.shop-pro.jp"
CATEGORY_ID = 2471964  # 珈琲豆(理由はモジュールdocstring参照)
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_items() -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.product-list__unit"):
        name_el = li.select_one("a.product-list__name")
        link_el = li.select_one('a[href^="?pid="]')
        if not name_el or not link_el:
            continue
        title = name_el.get_text(strip=True)
        soldout_el = li.select_one("span.product-list__soldout")
        price = None
        if not soldout_el:
            price_el = li.select_one("span.product-list__price")
            if price_el:
                m = PRICE_PATTERN.search(price_el.get_text())
                if m:
                    price = int(m.group(1).replace(",", ""))
        items.append({
            "title": title,
            "price": price,
            "out_of_stock": bool(soldout_el),
            "url": BASE_URL + "/" + link_el["href"],
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if not title:
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title, item["out_of_stock"])

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
        "price": item["price"],
        "weight_g": None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_items()

    records = []
    flavored_records = []
    for item in items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kurashikicoffeekan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kurashikicoffeekan.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
