# -*- coding: utf-8 -*-
"""
scrape_conami.py

こなみ珈琲(このなみこーひー、東京都中央区日本橋蛎殻町、水天宮前・人形町の
珈琲豆注文焙煎店)の商品情報を取得する。実店舗の案内サイト
(conamicoffee.com)自体は簡易なランディングページで、実際のオンライン
ショップは別ドメイン(conami.base.shop、BASE)で行われている「情報サイトと
通販サイトが別ドメイン」パターン(たまじ珈琲等と同様)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・MARUTAKE COFFEE BEANS等と同一の
記述(curl/python-requests等の一般的なHTTPクライアントは個別にDisallow: /
指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・/api/shops/・
違反報告ページ以外はAllow: /)。本スクレイパーは識別可能な独自User-Agentを
使用するため該当しない。

【カテゴリ構造について】
実データ確認済み: 27カテゴリすべてが「産地」(親、24件)配下の国別
サブカテゴリ(ブラジル/コロンビア/インドネシア等)で、ブレンド専用カテゴリは
存在しない。さらにsitemap.xml全42件中17件はどの産地カテゴリにも属さない
(新しいロットが未分類のまま、と考えられる)。カテゴリ横断でも漏れなく
全件を拾うため、GONZO CAFE&BEANS・BEANS珈琲と同じくカテゴリを使わず
sitemap.xmlの全itemsを対象にする。全42件を確認した限りギフトセットや
器具等の非コーヒー豆商品は無い(全件が「地名/銘柄名+重量」形式の単品豆)。

【商品説明について】
実データ確認済み: JSON-LD(schema.org Product)のdescriptionはカッピング
コメント中心の自由記述で、【生産国】等の構造化ラベルは無い。ロット名に
地名・農園名が使われるが必ずしも国名を含まない(例:「カタンドゥーバ・
ナチュラル」)ため、parse_product()で判定できない場合はorigin_country=null
のままとなる(GONZO CAFE&BEANSと同じ「構造化データ無し・商品名ベース」
パターン)。

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
    "name": "こなみ珈琲",
    "url": "https://conami.base.shop/",
    "platform": "BASE",
    "address": "東京都中央区日本橋蛎殻町1-39-2",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・MARUTAKE COFFEE BEANS等と"
                          "同一の記述。/cart/・/web_cart/・/shops/・/api/shops/・違反報告"
                          "ページ以外はUser-agent: *でAllow。curl/python-requests等は"
                          "個別にDisallow: /指定あり、本スクレイパーは識別可能な"
                          "User-Agentを使用)",
}

BASE_URL = "https://conami.base.shop"
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
        "weight_g": 200,  # 理由はモジュールdocstring参照(実データ確認済み、全商品200g固定)
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
    """理由はモジュールdocstring参照(カテゴリが実質機能しておらず、軽量な
    差分判定用raw_name取得元が無いため、GONZO CAFE&BEANS・BEANS珈琲と同じく
    毎回全件の詳細ページを取得する)。"""
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
        with open("data_conami.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_conami.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
