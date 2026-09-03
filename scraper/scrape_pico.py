# -*- coding: utf-8 -*-
"""
scrape_pico.py

カフェ・デザールピコ(cafe-pico-shop.com、東京都江東区門前仲町、24年の歴史)の
商品情報を取得する。カラーミーショップ(shop-pro.jp)。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ制限
(nericafe・麻布珈房等と同一の記述)。

【対象カテゴリについて】
実データ確認済み: 「スペシャルティコーヒーの人気ブレンドを通販」(2296084、
定番/季節限定/通販限定/店舗限定の4サブカテゴリの和集合、10件)・
「シングルオリジンのスペシャルティコーヒー通販」(2296086、インドネシア/
エチオピア/グァテマラ等の国別サブカテゴリの和集合、7件)・「新商品・数量限定
商品」(2287465、17件、月替りブレンドやスカラシップ対象豆等の実際のコーヒー豆
単品を含むが、ジェラート・アソートセット・ギフトセット等の非コーヒー豆商品も
混在)の3カテゴリを対象とする。「初回限定/送料無料セット」「人気のおすすめ
セット」「ドリップパック」「アイスコーヒー」「器具」「ギフトセット」は対象外。

【数量限定カテゴリの非コーヒー豆除外について】
実データ確認済み: NON_BEAN_KEYWORDSで「ジェラート」「ギフトセット」
「おすすめコーヒーセット」「ディップスタイル」「カフェオレのもと」
「お試しセット」を除外(自家製ジェラート、コーヒー2種アソートギフトセット、
ディップスタイルコーヒーバッグ、「初回限定スペシャルティコーヒーお試し
セット100ｇ×５種類入り」(5種の豆を詰め合わせたアソート)等、特定の一豆を
指さない商品)。「お試しセット」は実ワークフロー実行後のデータ検証で発覚
(手動調査時に見落とし)。

【重量について】
実データ確認済み: 商品名に重量表記が無く、商品説明文中の「価格：100ｇ690円」
という記述も商品ごとの実際の価格(sales_price)と一致しない(920円の商品でも
「100ｇ690円」のまま)、テンプレート文の使い回しで信頼できないことを確認済み。
不確かな値を採用せずweight_gはnullのままとする。

【在庫について】
inventory_controlが"none"、stock_numは常にnull(kunikuni.py・麻布珈房と
同じ運用)。商品名のテキストのみで在庫状態を判定する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "カフェ・デザールピコ",
    "url": "https://cafe-pico-shop.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都江東区門前仲町",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみ制限。"
                          "nericafe・麻布珈房等と同一の記述)",
}

BASE_URL = "https://cafe-pico-shop.com"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "2296084": "ブレンド",
    "2296086": "シングルオリジン",
    "2287465": "新商品・数量限定",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ジェラート", "ギフトセット", "おすすめコーヒーセット", "ディップスタイル",
                     "カフェオレのもと", "お試しセット"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)


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

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

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
    stock_status = detect_stock_status(title)

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
        "weight_g": None,  # 理由はモジュールdocstring参照(信頼できる重量情報が無い)
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
    seen = set()
    for link_el in soup.select('a.product-list__name[href*="pid="]'):
        href = link_el.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        title = link_el.get_text(strip=True)
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_pico.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_pico.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
