# -*- coding: utf-8 -*-
"""
scrape_horicoffee.py

ホリ珈琲(hori-coffee.co.jp、三重県桑名市中央町2-11〈桑名本店〉、
1968年創業の老舗自家焙煎珈琲店、5拠点展開(桑名本店・ロースタリー店・
四日市店・アピタ松阪三雲店・アピタ桑名店、11店舗未満のため対象)の
商品情報を取得する。WordPress+Welcart(usces-cart/usces-memberという
URLパスから確認済み。usces=Welcartのショッピングカートエンジン名
「Universal Shopping Cart Engine」の略)。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/のみ
Disallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う公開商品
ページ・カテゴリページは制限対象外。

【商品情報の取得方法について】
実データ確認済み: 大和屋珈琲(scrape_yamatoya.py)と異なりこの店舗のテーマ
(welcart_basic-child)は商品ページにJSON-LD構造化データを一切出力して
いない(実データ確認済み、`application/ld+json`が0件)。商品名は
h1.firstset_skuTxt__hl、価格はdiv.firstset_skuTxt__price内の数字を
直接HTMLから取得する。在庫状態はdiv.zaikostatusの文言(「在庫状態 :
在庫有り」等)から構造化フラグとして取得できる(実データ確認済み)。

【商品一覧の取得方法について】
実データ確認済み: カテゴリページ4つ(coffee/specialty_coffee・
coffee/blend-coffee・superb-coffee・jitakuyou)を取得し、含まれる
商品リンクを和集合で収集する(大和屋珈琲と同じ「まめぽっと」方式)。
jitakuyouカテゴリは実質的にspecialty_coffee+blend-coffeeの豆売り商品を
包含する「自宅用」カテゴリと確認済みだが、念のため4カテゴリすべてを
和集合対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記4カテゴリに含まれる商品のうち、ドリップパック/
ドリップバッグ各種(「ホリブレンド ドリップパック 8/12/30袋」
「デカフェ ドリップコーヒー3/8/12/30枚」「極上ブルマンブレンド
ドリップバッグ/ドリップコーヒー」等)・ギフトセット・アイスコーヒー
(瓶入りリキッド)がコーヒー豆単品ではないため
NON_BEAN_KEYWORDSで除外する。残り8件(ホリブレンドNo.18・
ブルーマウンテンNO1・コスタリカハニー中浅煎り・トミオフクダDOT・
アロマモカプリンセス・スウィートダークロースト・極上ブルマンブレンド・
デカフェオーガニックコーヒー、いずれも200g)を対象とする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ホリ珈琲",
    "url": "https://hori-coffee.co.jp/",
    "platform": "Welcart",
    "address": "三重県桑名市中央町2-11",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/のみDisallow、"
                          "本スクレイパーが使う公開商品ページは制限対象外)",
}

BASE_URL = "https://hori-coffee.co.jp"
CATEGORY_PATHS = [
    "category/item/coffee/specialty_coffee/",
    "category/item/coffee/blend-coffee/",
    "category/item/superb-coffee/",
    "category/item/jitakuyou/",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップ", "ギフト", "セット", "アイスコーヒー", "プリン", "チーズケーキ"]
EXCLUDE_URL_SUFFIXES = ("usces-cart/", "usces-member/", "company/", "contact/", "info/",
                         "kodawari/", "privacy-policy/", "teiki-change/", "teikibin/", "wp-json/")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    urls: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select(f'a[href^="{BASE_URL}/"]'):
            href = a.get("href", "")
            m = re.match(rf"^{re.escape(BASE_URL)}/([a-z0-9-]+)/$", href)
            if not m:
                continue
            if href.endswith(EXCLUDE_URL_SUFFIXES):
                continue
            urls.add(href)
    return sorted(urls)


def build_record(html: str, product_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("h1.firstset_skuTxt__hl")
    if not title_el:
        return None
    title = re.sub(r"\s+", " ", title_el.get_text(strip=True)).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one("div.firstset_skuTxt__price span.big")
    price = None
    if price_el:
        price_digits = re.sub(r"[^\d]", "", price_el.get_text())
        price = int(price_digits) if price_digits else None

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

    zaiko_el = soup.select_one("div.zaikostatus")
    structural_out_of_stock = bool(zaiko_el) and "在庫有り" not in zaiko_el.get_text()
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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_soup = BeautifulSoup(html, "html.parser")
        title_el = title_soup.select_one("h1.firstset_skuTxt__hl")
        title = re.sub(r"\s+", " ", title_el.get_text(strip=True)).strip() if title_el else ""
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(html, product_url)
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
    with open("data_horicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_horicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
