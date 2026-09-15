# -*- coding: utf-8 -*-
"""
scrape_oyamacoffee.py

小山珈琲(Oyama Coffee、oyamacoffee-shop.com、〒811-1311
福岡市南区横手2-16-1 岡村ビル1階)の商品情報を取得する。カラーミー
ショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://oyamacoffee-shop.com/?mode=sk)で
「〒8111311 福岡県福岡市南区横手2-16-1 岡村ビル1階」を確認済み
(2026-09時点、EUC-JPで直接デコードして確認)。WebFetch経由の要約では
北九州市八幡西区の別住所に誤変換されたため、必ずrequestsでの直接
デコード結果を採用すること。

【文字コードについて】
実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【価格表示・重量について】
実データ確認済み: 注文後焙煎(ロースト・トゥ・オーダー)方式で、
一覧ページの時点で`p.prd-lst-price`に「820円／100g」のように100gあたり
単価が直接出力されている(Rhizomagと同じprd-lst-unitテーマだが、この
店舗は挽き方違いの複数バリアントが全て同一単価のため、詳細ページを
個別に取得せず一覧ページの情報のみでweight_g=100の代表レコードとして
出力する)。

【非コーヒー豆商品の除外について】
実データ確認済み: 一覧に器具・ギフト・詰め合わせセットは見つからず、
全件が単一銘柄のストレート/ブレンドだった。念のためNON_BEAN_KEYWORDSを
用意しておく。

robots.txt確認済み(2026-09時点): shop-pro.jp標準の記述で、本スクレイパーが
使う一覧ページ(?mode=srh)は制限対象外。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "小山珈琲",
    "url": "https://oyamacoffee-shop.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県福岡市南区横手2-16-1 岡村ビル1階",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、"
                          "本スクレイパーが使う一覧ページは制限対象外)",
}

BASE_URL = "https://oyamacoffee-shop.com"
LIST_BASE_URL = "https://oyamacoffee-shop.com/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ギフト", "セット", "器具"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
UNIT_WEIGHT_G = 100  # 理由はモジュールdocstring参照(100gあたり単価表示)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.prd-lst-unit"):
        name_el = li.select_one(".prd-lst-name a")
        if not name_el:
            continue
        title = name_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        href = name_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href

        soldout_el = li.select_one(".prd-lst-soldout")
        price = None
        if not soldout_el:
            price_el = li.select_one(".prd-lst-price")
            if price_el:
                m = PRICE_PATTERN.search(price_el.get_text())
                if m:
                    price = int(m.group(1).replace(",", ""))

        items.append({
            "raw_name": title,
            "product_url": product_url,
            "price": price,
            "out_of_stock": bool(soldout_el),
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title, item.get("out_of_stock", False))

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
        "weight_g": UNIT_WEIGHT_G,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


MAX_PAGES = 30  # 安全のための上限(shop-pro.jpの一部店舗は総件数の少ないページ番号を
# 超えて指定しても最終ページの内容を繰り返し返すことがあるため、新規URLが
# 増えなくなった時点で打ち切る仕組みと併用する)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    seen_urls = set()
    page = 1
    while page <= MAX_PAGES:
        items = scrape_list_page(page)
        new_items = [i for i in items if i["product_url"] not in seen_urls]
        if not new_items:
            break
        for i in new_items:
            seen_urls.add(i["product_url"])
        all_items.extend(new_items)
        page += 1

    records = []
    flavored_records = []
    for item in all_items:
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
    with open("data_oyamacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oyamacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
