# -*- coding: utf-8 -*-
"""
scrape_matsuya.py

松屋珈琲店(まつやこーひーてん、東京都港区虎ノ門、大正7年創業)の商品情報を
取得する。実店舗サイト(la-vie-en-cafe.co.jp)自体は会社案内・卸売案内が
中心で、実際のオンラインショップは別ドメイン(la-vie-en-cafe.com、カラーミー
ショップ)で行われている「情報サイトと通販サイトが別ドメイン」パターン
(たまじ珈琲・MARUTAKE COFFEE BEANSと同様)。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ制限
(nericafe・麻布珈房等と同一の記述)。

【対象カテゴリについて】
実データ確認済み: 「Blend Coffee」(600493、10件)・「Single Coffee」
(600974、9件)・「Limited Selection」(2664459、7件、産地限定シングル
オリジン)の3カテゴリがコーヒー豆単品を指す。「Drip Bag」(2071917)・
「Gift Set」(2834961)・「Goods」(2936537)・「コーヒー関連器具」(601421)は
対象外。

【商品名が英語表記であることについて】
実データ確認済み: 全商品名が英語表記(例:"Peru Achamal Village Takahashi /
Geisha Washed Process 200g"、"House Blend")。coffee_parser.pyの
ORIGIN_COUNTRY_KEYWORDS_EN(英語国名)・BLEND_KEYWORDS(大文字小文字無視で
"blend"も検出)で概ねカバーできる。

【在庫について】
実データ確認済み: var Colormeのinventory_controlが商品ごとに"product"
(在庫数を実際に管理、stock_numに実数)と"none"(stock_numは常にnull)の
どちらもあり、店舗全体で統一されていない(nericafe・麻布珈房は全商品
"none"だったため、この店舗固有の混在パターン)。実ワークフロー実行後の
データ検証で発覚: "none"の商品にもstock_num<=0の品切れ判定を無条件適用
すると、全26件中House Blend等25件が誤って「一時的に品切れ」になっていた。
inventory_control=="product"の商品にのみ構造的な品切れ判定を適用し、
"none"の商品は商品名のテキストのみで判定するよう修正した。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "松屋珈琲店",
    "url": "https://www.la-vie-en-cafe.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都港区虎ノ門3-8-16",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみ制限。"
                          "nericafe・麻布珈房等と同一の記述)",
}

BASE_URL = "https://www.la-vie-en-cafe.com"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "600493": "Blend Coffee",
    "600974": "Single Coffee",
    "2664459": "Limited Selection",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def build_record(product_url: str, colorme_product: dict, category_hint: str) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    price = colorme_product.get("sales_price_including_tax")

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

    # 理由はモジュールdocstring参照。inventory_controlは商品ごとに"product"
    # (在庫数を実際に管理)/"none"(管理していない、stock_numは常にnull)が
    # 混在しており、"none"の商品にstock_num<=0の判定をそのまま適用すると
    # 全件が誤って品切れ扱いになる不具合を実データで確認済み。
    structural_out_of_stock = (
        colorme_product.get("inventory_control") == "product"
        and (colorme_product.get("stock_num") or 0) <= 0
    )
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "weight_g": (lambda m: int(m.group(1)) if m else None)(WEIGHT_PATTERN.search(title)),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, colorme_product, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    results = []
    for link_el in soup.select('a.c-product-list__name[href*="pid="]'):
        href = link_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        title = link_el.get_text(strip=True)
        results.append({"raw_name": title, "product_url": product_url})
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
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            elif not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_matsuya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_matsuya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
