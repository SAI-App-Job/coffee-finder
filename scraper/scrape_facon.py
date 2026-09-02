# -*- coding: utf-8 -*-
"""
scrape_facon.py

CAFE FACON(cafe-facon.jp、東京都目黒区・渋谷区)の商品情報を取得する。
ShopServe(ショップサーブ)というMui(scrape_mui.py)と同じプラットフォームだが、
店舗ごとのテーマ・運用がMuiとは大きく異なる(実データ確認済み、2026-09時点)。

robots.txt確認済み(2026-09時点): cafe-facon.jp・www.cafe-facon.jpどちらも
robots.txt自体が存在しない(404)。Mui(mui-motosumi.co.jp)と同じくShopServe
標準の状態と見られ、実質全面許可とみなせる。

【対象カテゴリについて】
ユーザー指定の2カテゴリ、SHOP/11929(「オリジナルブレンドから選ぶ」、ブレンド)・
SHOP/11931(「産地から選ぶ（シングルオリジン）」、シングルオリジン)を対象とする。
実データ確認済み: 11929は7件(1ページ、list2.htmlは0件で終端)、11931は19件
(2ページ、list3.htmlは0件で終端)で、いずれもスイーツ・器具等コーヒー豆以外の
商品は混在していなかった(この2カテゴリ自体がコーヒー豆専用のため、
NON_BEAN_KEYWORDSによる除外処理は不要)。ページ送りは/SHOP/<カテゴリID>/
list<N>.html(N=1,2,...、Muiと異なり/t02/を含まない)。

【商品詳細ページを個別に取得しない理由】
実データ確認済み(facon001・facon0004等、ブレンド/シングルオリジン双方で確認):
詳細ページにはMui(gtag view_item・table.info-table)のような構造化データが
一切無く、価格(table.price)は一覧ページの表示と完全に一致し、産地・精選方法・
品種・標高等の説明文自体が存在しない(挽き方選択オプションのみ)。そのため
詳細ページを個別に取得する意味が無く、一覧ページの情報(商品名・価格・在庫)
だけで完結させる。産地・精選方法・焙煎度・グレード・特定銘柄はすべて商品名
から判定する(coffee_parser.parse_product()。例:「エチオピア　グジ　ゴロ・
ベデッサ　ナチュラル　シティロースト　200g」のように精選方法・焙煎度が
商品名にそのまま書かれているため、追加のパースロジックが無くても十分な
精度で取得できる)。

【在庫状態について】
実データ確認済み: 一覧ページのp.sps-itemList-stockDisp要素が「在庫切れ」の
テキストを持つ商品が複数確認できた(Muiのような在庫数表記ではなくテキストの
有無で判定する)。これを構造的な品切れシグナルとして使う。

【拠点情報について】
中目黒本店・代官山ロースターアトリエの2拠点。cafe-facon.jp(ShopServe側)には
店舗の住所・営業時間の記載が無く、系列サイトcafefacon.com(基本情報サイト、
nakameguro.html・roasteratelier.html)に記載があったため、そちらから固定で
取得する(WOODBERRY COFFEEのように動的な店舗一覧ページを持たないため、
2ページを直接fetchする方式)。「本店」を名乗る中目黒本店をis_headquartersとする。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "CAFE FACON",
    "url": "https://cafe-facon.jp/",
    "platform": "ShopServe",
    "address": "東京都目黒区上目黒3-8-3 千陽中目黒ビル・アネックス3F",
    "prefecture": "東京都",
    "robots_txt_status": "robots.txtなし(2026-09確認。cafe-facon.jp・www.cafe-facon.jpどちらも"
                          "404で存在しない。Muiと同じくShopServe標準の状態で、実質全面許可とみなせる)",
}

BASE_URL = "https://cafe-facon.jp"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(ユーザー指定の2カテゴリ、いずれもコーヒー豆専用)
LIST_CATEGORIES = {
    "11929": "ブレンド",
    "11931": "シングルオリジン",
}

PRICE_PATTERN = re.compile(r"([\d,]+)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# 理由はモジュールdocstring参照(cafefacon.comの店舗紹介ページから固定取得)
LOCATIONS = [
    {
        "label": "中目黒本店",
        "address": "東京都目黒区上目黒3-8-3 千陽中目黒ビル・アネックス3F",
        "prefecture": "東京都",
        "hours": "10:00〜22:00(定休日：不定休)",
        "tel": "03-3716-8338",
        "is_headquarters": True,
        "map_query": "CAFE FACON 中目黒本店",
    },
    {
        "label": "代官山ロースターアトリエ",
        "address": "東京都渋谷区代官山町10-1",
        "prefecture": "東京都",
        "hours": "10:00〜19:00(定休日：不定休)",
        "tel": "03-6416-5858",
        "is_headquarters": False,
        "map_query": "CAFE FACON 代官山ロースターアトリエ",
    },
]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def scrape_category_list_page(cid: str, page: int) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/SHOP/{cid}/list{page}.html")

    results = []
    for card in soup.select("section.column4"):
        title_el = card.select_one("div.itemThumb-wrap-right h2 a")
        if not title_el:
            continue
        raw_name = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("/") else href

        price = None
        price_el = card.select_one("p.price span.selling_price")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        stock_el = card.select_one("p.sps-itemList-stockDisp")
        structural_out_of_stock = bool(stock_el and "在庫切れ" in stock_el.get_text())

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "structural_out_of_stock": structural_out_of_stock,
        })
    return results


def scrape_category_list(cid: str) -> list[dict]:
    all_items = []
    page = 1
    while True:
        items = scrape_category_list_page(cid, page)
        if not items:
            break
        all_items.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return all_items


def build_record(item: dict, category_hint: str) -> dict:
    raw_name = item["raw_name"]
    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(raw_name, item["structural_out_of_stock"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
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
        "price": item["price"],
        "weight_g": parse_weight(raw_name),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"], price=item["price"]):
            records.append(prev)
            continue

        detail = build_record(item, item["category_hint"])
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()

    shop_info = dict(SHOP_INFO)
    shop_info["locations"] = LOCATIONS

    output = {
        "shop": shop_info,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }

    with open("data_facon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_facon.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
