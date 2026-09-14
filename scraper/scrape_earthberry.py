# -*- coding: utf-8 -*-
"""
scrape_earthberry.py

EARTH BERRY COFFEE(ebcoffee.shop-pro.jp、〒739-0014 広島県広島市中区
紙屋町6-2 紙屋町ビル1F、自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページを実データ確認したところ、候補リストで「東広島市
西条(市レベルのみ)」とされていた住所は誤りで、実際は「〒739-0014
広島県広島市中区紙屋町6-2 紙屋町ビル1F」であることを確認した(2026-09
時点)。

robots.txt確認済み(2026-09時点): shop-pro.jp標準のrobots.txtで、本
スクレイパーが使う商品一覧・詳細ページ(?mode=cate, ?pid=)は制限対象外。

【対象カテゴリについて】
実データ確認済み: 商品カテゴリは「ドリップバック(一杯コーヒー、
cbid=1858783)」「アースベリーブレンド(1864343)」「ビターベリーブレンド
(1864973)」「カフェインレスコーヒー(1984578)」「クラシックブレンド
(2075472)」「グァテマラ カブレホ農園(2297631)」「エチオピア シダモ
ボナセダカ(2412279)」「コロンビア カンポベッロ(2434930)」「コスタリカ
エルパライソ農園ナチュラル(2543154)」「カフェオレベース(2724236)」
「ギフトセット(2773375)」「【期間限定】オータムブレンド(2782120)」の
12種類。ドリップバック・カフェオレベース・ギフトセットの3カテゴリは
非対象(コーヒー豆単品ではない)、残り9カテゴリを対象とする。

【卸価格・まとめ買いの重複について】
実データ確認済み: 各銘柄は200g(通常価格)/500g(20%OFF)/1kg(25〜30%OFF、
500g×2袋)/3kg(30%OFF、卸価格、500g×6袋)の4種類の重量・卸値引き表記で
別商品ページが存在する。500g以上の商品名にはいずれも「OFF」の文字列が
含まれる(実データ確認済み、全パターンで一致)ため、これをキーワードとして
除外し、基準となる200gの商品のみを対象とする。「【期間限定】オータム
ブレンド」は複数カテゴリに重複掲載されているため、pid(商品ID)で重複
排除する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "EARTH BERRY COFFEE",
    "url": "https://ebcoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "広島県広島市中区紙屋町6-2 紙屋町ビル1F",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、本スクレイパーが"
                          "使う商品一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://ebcoffee.shop-pro.jp"
CATEGORY_IDS = [1864343, 1864973, 1984578, 2075472, 2297631, 2412279, 2434930, 2543154, 2782120]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["OFF"]  # 理由はモジュールdocstring参照(500g以上のまとめ買い/卸を除外)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category(cbid: int) -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0&sort=n"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.product-list__unit"):
        link_el = li.select_one('a[href^="?pid="]')
        name_el = li.select_one("a.product-list__name, span.product-list__name")
        if not link_el or not name_el:
            continue
        title = name_el.get_text(strip=True)
        title = re.sub(r"\s+", " ", title)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        soldout_el = li.select_one("span.product-list__soldout")
        price = None
        if not soldout_el:
            price_el = li.select_one("span.product-list__price")
            if price_el:
                m = PRICE_PATTERN.search(price_el.get_text())
                if m:
                    price = int(m.group(1).replace(",", ""))
        pid_m = re.search(r"pid=(\d+)", link_el["href"])
        items.append({
            "pid": pid_m.group(1) if pid_m else link_el["href"],
            "title": title,
            "price": price,
            "out_of_stock": bool(soldout_el),
            "url": BASE_URL + "/" + link_el["href"],
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: dict[str, dict] = {}
    for cbid in CATEGORY_IDS:
        try:
            items = scrape_category(cbid)
        except requests.RequestException as e:
            print(f"[warn] カテゴリ取得失敗: cbid={cbid} ({e})")
            continue
        for item in items:
            all_items[item["pid"]] = item

    records = []
    flavored_records = []
    for item in all_items.values():
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
    with open("data_earthberry.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_earthberry.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
