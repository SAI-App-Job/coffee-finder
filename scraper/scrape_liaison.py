# -*- coding: utf-8 -*-
"""
scrape_liaison.py

ブーランジェリー エ カフェ リエゾン(www.liaison-iga.com、三重県伊賀市
小田町701-1、熱風自家焙煎のコーヒーと国産小麦100%パンの店)の商品情報を
取得する。

【プラットフォームについて】
実データ確認済み: BASE/カラーミー/Shopify/Ocnk/Welcart/MakeShop/
WooCommerce/EC-CUBEのいずれの指紋にも一致しない、汎用ショッピングカート
CMS(CSSが`ssl.xaas3.jp`から配信され、追跡スクリプトのドメイン識別子が
`m4130239`という固有店舗コード形式になっている。ベンダー名不明の
中小事業者向けASPカート)。カテゴリ一覧`/category/<ID>/`→商品詳細
`/item/<ID>/`という単純なURL構造で、商品名・価格・在庫状態がすべて
サーバーサイドレンダリングの静的HTMLに直接含まれているため、
プラットフォーム名が特定できなくても標準的なrequests+BeautifulSoupで
問題なく取得できることを確認済み。全カテゴリ合計で商品はわずか5件
(ブレンド4件・ストレート1件)という小規模店舗。

robots.txt確認済み(2026-09時点、www.liaison-iga.comへの301リダイレクト後):
`Disallow: /default/error/` `Disallow: /preview/` のみ。本スクレイパーが
使うcategory/itemページは制限対象外。

【商品一覧の取得方法について】
実データ確認済み: カテゴリ1(ブレンド)に4件、カテゴリ2(ストレート)に
1件、カテゴリ3・5・6・7は空(0件)。全カテゴリを巡回して商品リンクの
和集合を取る。

【非コーヒー豆商品の除外について】
実データ確認済み(全5件): カテゴリ1の4件中3件
(「IGATETSU COFFEEドリップパック...」×2、「IGATETSU COFFEEドリップ
２４個...」)がドリップパック形式でコーヒー豆単品ではないため
NON_BEAN_KEYWORDSの「ドリップ」で除外する。残り2件
(「リエゾンブレンド　150g ×2袋」「ブラジルサントスNo.2　150g×2袋」)
を対象とする。いずれも150g×2袋(合計300g)の梱包だが、単一銘柄の
豆売り商品であるため対象に含める。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ブーランジェリー エ カフェ リエゾン",
    "url": "https://www.liaison-iga.com/",
    "platform": "不明(独自/中小事業者向けASPカート、xaas3.jp)",
    "address": "三重県伊賀市小田町701-1",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/と/preview/のみ"
                          "Disallow、本スクレイパーが使うcategory/itemページは"
                          "制限対象外)",
}

BASE_URL = "https://www.liaison-iga.com"
CATEGORY_IDS = [1, 2, 3, 5, 6, 7]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"(\d[\d,]*)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    urls: set[str] = set()
    for cat_id in CATEGORY_IDS:
        soup = fetch_page(f"{BASE_URL}/category/{cat_id}/")
        for a in soup.select(f'a[href^="{BASE_URL}/item/"]'):
            href = a.get("href", "")
            if re.match(rf"^{re.escape(BASE_URL)}/item/[a-z0-9]+/$", href):
                urls.add(href)
    return sorted(urls)


def extract_title(soup: BeautifulSoup) -> str:
    # 商品名はul.spec > li.name > p.data > span.data にある(実データ確認済み)。
    # h1タグはヘッダーのショップロゴ(店名)であり商品名ではないため使わない。
    title_el = soup.select_one("li.name span.data")
    return title_el.get_text(strip=True) if title_el else ""


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title = extract_title(soup)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price = None
    price_el = soup.select_one("li.sales_price span.data")
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

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

    stock_el = soup.select_one("li.stock1 p.data")
    stock_text = stock_el.get_text(strip=True) if stock_el else ""
    structural_out_of_stock = bool(stock_text) and "在庫あり" not in stock_text
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
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title = extract_title(soup)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(soup, product_url)
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
    with open("data_liaison.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_liaison.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
