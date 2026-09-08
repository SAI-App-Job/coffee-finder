# -*- coding: utf-8 -*-
"""
scrape_greatcoffee.py

自家焙煎「キャビン珈琲」(greatcoffee.jp、兵庫県三田市けやき台5-5-10、
自家焙煎豆のオンライン販売)の商品情報を取得する。ShopServe。本プロジェクト
で初めてのShopServe店舗。

【プラットフォームについて】
実データ確認済み: 商品画像がimage1.shopserve.jpドメインで配信されており、
URL構造(/SHOP/<商品コード>.html、カテゴリ一覧は/SHOP/<カテゴリID>/
list.html)からShopServe(GMOメイクショップ系ではなく、インターファクトリー
社のShopServe)であることを確認した。カラーミー/BASE/Shopify/Ocnk/
WooCommerce/EC-CUBEのいずれにも該当しない新規プラットフォームだが、
一覧ページに商品名・価格が静的HTMLでそのまま出力されており(JS実行不要)、
詳細ページの`var stockInfo = '...'`から在庫状況も取得できるため、
低リスクな抽出方法として実装する。

robots.txt確認済み(2026-09時点): www.greatcoffee.jpにrobots.txt自体が
存在しない(404)。User-agent別の制限記述が一切ないため、実質的に
クロール制限なしと判断した。

【商品一覧の取得方法について】
実データ確認済み: トップページのナビゲーションに「コーヒー豆（２００ｇ
入袋）」配下の「ブレンド豆」(/SHOP/28021/28022/list.html)と「ストレート豆」
(/SHOP/28021/28027/list.html)の2カテゴリに計6銘柄、「お任せ（お勧め）
セット」(/SHOP/98240/list.html)に2件、「お任せ（お勧め）セット割引」
(/SHOP/g18398/list.html)は現在0件。カテゴリ一覧ページから商品名・価格・
詳細URLを取得する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「お任せ（お勧め）1.0kg セット」「お任せ（お勧め）
セット　800g」(複数銘柄の詰め合わせ、単一銘柄でないため)が非対象。
NON_BEAN_KEYWORDSで除外する。残り6件(キリマンブレンド「望」・
マイルドブレンド「心」・トラジャーブレンド「道」・Colombia(Bourbon)・
トラジャ ママサ プレミアム・Guatemala(Bourbon 100%)、いずれも200g)を
対象とする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎 キャビン珈琲",
    "url": "https://www.greatcoffee.jp/",
    "platform": "ShopServe",
    "address": "兵庫県三田市けやき台5-5-10",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。www.greatcoffee.jpにrobots.txt自体が"
                          "存在せず(404)、クロール制限の記述がないため実質無制限と判断)",
}

BASE_URL = "https://www.greatcoffee.jp"
# 実データ確認済み: 「ブレンド豆」「ストレート豆」は2系統のカテゴリツリー
# (/SHOP/28021/配下と/SHOP/g1219x/配下)から重複して参照されており、
# 片方だけでは商品が漏れる(例: キリマンブレンド「望」はg12191にのみ掲載)
# ため、両方を巡回してURLで重複排除する。お任せセット系カテゴリも将来の
# 単一銘柄追加に備えて巡回対象に含め、NON_BEAN_KEYWORDSで除外する。
CATEGORY_PATHS = [
    "/SHOP/28021/28022/list.html",  # ブレンド豆
    "/SHOP/28021/28027/list.html",  # ストレート豆
    "/SHOP/g12191/list.html",       # ブレンド豆(別カテゴリツリー)
    "/SHOP/g12192/list.html",       # ストレート豆(別カテゴリツリー)
    "/SHOP/98240/list.html",        # お任せ(お勧め)セット
    "/SHOP/g18398/list.html",       # お任せ(お勧め)セット割引
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["お任せ", "セット"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
STOCK_INFO_PATTERN = re.compile(r"var\s+stockInfo\s*=\s*'([^']*)'")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_list() -> list[dict]:
    # 実データ確認済み: 商品名リンクは<h2 class="goods"><a href="/SHOP/xxx.html">
    # 商品名</a></h2>、価格はその直後の兄弟要素<div class="price">に入っている
    # (同じ<td>内)。
    items: dict[str, dict] = {}
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}{path}")
        for h2 in soup.select("h2.goods"):
            a = h2.find("a", href=re.compile(r"^/SHOP/[A-Za-z0-9]+\.html$"))
            if not a:
                continue
            product_url = BASE_URL + a["href"]
            if product_url in items:
                continue
            title = a.get_text(strip=True)
            price = None
            price_el = h2.find_next_sibling("div", class_="price")
            if price_el:
                m = PRICE_PATTERN.search(price_el.get_text())
                if m:
                    price = int(m.group(1).replace(",", ""))
            if title:
                items[product_url] = {"title": title, "price": price, "url": product_url}
    return list(items.values())


def fetch_stock_status(product_url: str) -> str | None:
    try:
        resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    m = STOCK_INFO_PATTERN.search(resp.text)
    return m.group(1) if m else None


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
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

    stock_info = fetch_stock_status(item["url"])
    structural_out_of_stock = bool(stock_info) and "あり" not in stock_info
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_item_list()

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
    with open("data_greatcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_greatcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
