# -*- coding: utf-8 -*-
"""
scrape_beanscoffee.py

BEANS珈琲(beanscoffee.base.ec、東京都墨田区、注文後焙煎の直火式小型焙煎機)の
商品情報を取得する。BASEの白ラベルドメイン「.base.ec」(GONZO CAFE&BEANSの
「.base.shop」、MARUTAKE COFFEE BEANSの「.official.ec」、隠房の「.theshop.jp」に
続く、この項目で確認済みの4つ目のBASEドメインバリエーション)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・MARUTAKE COFFEE BEANS・GONZO
CAFE&BEANS等と同一の記述(curl/python-requests等の一般的なHTTPクライアントは
個別にDisallow: /指定があるが、User-agent: *ルールでは/cart/・/web_cart/・
/shops/・/api/shops/・違反報告ページ以外はAllow: /)。本スクレイパーは
識別可能な独自User-Agentを使用するため該当しない。

【カテゴリ構造について】
実データ確認済み: GONZO CAFE&BEANSと同じく、カテゴリはすべて「口当たりが
柔らかい味」「コク・苦みが強い味」等の味わい別の横断的な分類(重複ビュー)で、
sitemap.xmlに列挙された21件のitems/<ID>が全商品(フラットな一覧)。全21件を
確認したところ、全て170g固定のコーヒー豆単品で、非コーヒー豆商品は無いことを
確認済み。

【商品説明について】
実データ確認済み: JSON-LD(schema.org Product)のdescriptionはマーケティング
文言のみで構造化欄は無い。商品名自体に産地・銘柄(トラジャ、キリマンジャロ、
モカ等)が含まれているため、parse_product()の商品名解析で十分カバーできる
(GONZO CAFE&BEANSと同じ「構造化データ無し・商品名ベース」パターン)。

【価格・在庫について】
JSON-LD(schema.org Product)のoffersにprice・availability
(http://schema.org/InStock 等)が構造化されている(GONZO CAFE&BEANS・
MARUTAKE COFFEE BEANSと同じBASE標準テンプレート)。
"""

import json
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "BEANS珈琲",
    "url": "https://beanscoffee.base.ec/",
    "platform": "BASE",
    "address": "東京都墨田区",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・MARUTAKE COFFEE BEANS・"
                          "GONZO CAFE&BEANS等と同一の記述。/cart/・/web_cart/・"
                          "/shops/・/api/shops/・違反報告ページ以外はUser-agent: *で"
                          "Allow。curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://beanscoffee.base.ec"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def build_record(product_url: str, product: dict) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        price = int(offers["price"]) if offers.get("price") is not None else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "weight_g": 170,  # 理由はモジュールdocstring参照(全商品170g固定)
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "/items/" in text:
            urls.append(text)
    return urls


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    """理由はモジュールdocstring参照(カテゴリが無くsitemap.xmlのみで
    軽量な差分判定用raw_nameが取得できないため、GONZO CAFE&BEANSと同じく
    毎回全件の詳細ページを取得する。21件・CRAWL_DELAY_SECONDS=1.5秒でも
    1分弱に収まる)。"""
    product_urls = fetch_sitemap_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail.get("is_flavored"):
            flavored_records.append(detail)
        elif not detail.get("non_bean"):
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

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
        with open("data_beanscoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_beanscoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
