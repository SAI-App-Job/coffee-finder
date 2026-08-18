# -*- coding: utf-8 -*-
"""
scrape_nagi.py

NAGI COFFEE(神奈川県横浜市神奈川区反町)の商品情報を取得する。公式サイト
(nagicoffee.com)自体はJimdo製の情報サイトで通販機能を持たず、実際の販売は
別ドメインのTHE SHOP(nagicoffee.theshop.jp、BASE系のショッピングカートSaaS)
上で行われている(実データ確認済み、2026-08時点)。

robots.txt確認済み: THE SHOP側は`curl`/`python-requests`/`aiohttp`等の
一般的なHTTPクライアントのUser-Agentを名指しでDisallow: /にしているが、
`User-Agent: *`ルールでは/cart/・/web_cart/・/shops/・/api/shops/以外は
Allow: /となっている。本スクレイパーは商品情報の取得に/items/(商品詳細)と
/categories/(カテゴリ一覧)のみを使用し、いずれもDisallow対象に含まれない。
念のためUser-Agentは`requests`のデフォルト値ではなく本プロジェクト共通の
識別可能な文字列(CoffeeFinderBot/0.1)を明示的に設定している。

【対象カテゴリについて】
サイト側の商品タクソノミーが「コーヒー豆（HOT用）」(cid=1064782)と
「コーヒー豆（ICE用）」(cid=1064783)という2カテゴリにコーヒー豆商品を
分離しており、これ以外(コーヒーはちみつ／その他／ボックス／フィルター／
アイスコーヒーリキッド／ディップコーヒーバッグ)は非コーヒー豆・別形態の
商品であることを実データ調査で確認済み。そのためこの2カテゴリのみを
対象とし、キーワードベースの非コーヒー豆除外ロジックは持たない。

【商品説明の構造】
p.explanation[itemprop="description"]は自由記述の段落で、店舗ごとの構造化
ラベルはほぼ無い(「内容量：200g」のような重量表記が稀に含まれる程度)。
産地・精選方法・グレードは主に商品名(例:「スマトラ マンデリンG1(200g)」)
からcoffee_parser.parse_product()で判定する。重量は商品名末尾の
"(数字g)"パターンを優先し、無ければ説明文の「内容量：」表記にフォールバックする。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    extract_from_description,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "NAGI COFFEE",
    "url": "https://www.nagicoffee.com/",
    "platform": "THE SHOP(BASE系)",
    "address": "神奈川県横浜市神奈川区松本町3-22-8",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(2026-08確認。/cart/・/web_cart/・/shops/・/api/shops/以外は"
                          "User-agent: *でAllow。curl/python-requests等は個別に"
                          "Disallow: /指定あり、本スクレイパーは識別可能なUser-Agentを使用)",
}

CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

LIST_CATEGORY_URLS = [
    "https://nagicoffee.theshop.jp/categories/1064782",  # コーヒー豆（HOT用）
    "https://nagicoffee.theshop.jp/categories/1064783",  # コーヒー豆（ICE用）
]

WEIGHT_PATTERN = re.compile(r"\((\d+)\s*g\)")
WEIGHT_LABEL_PATTERN = re.compile(r"内容量：\s*(\d+)\s*g")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def build_record(product_url: str, title: str, description_text: str, price: int | None) -> dict:
    parsed = parse_product(title)

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

    extra = extract_from_description(description_text)
    if extra["processing_method"] and not parsed["processing_method"]:
        parsed["processing_method"] = extra["processing_method"]
    parsed = apply_category_hint_fallback(parsed, None)

    weight_g = None
    m = WEIGHT_PATTERN.search(title)
    if m:
        weight_g = int(m.group(1))
    else:
        m = WEIGHT_LABEL_PATTERN.search(description_text or "")
        if m:
            weight_g = int(m.group(1))

    farm_note = f"品種: {extra['variety_note']}" if extra.get("variety_note") else None

    stock_status = detect_stock_status(title)

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
        "roast_hint": None,
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": None,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)

    title_el = soup.select_one('h2[itemprop="name"]')
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = soup.select_one('[itemprop="offers"] .price')
    price = None
    if price_el:
        price_match = re.search(r"([\d,]+)", price_el.get_text())
        if price_match:
            price = int(price_match.group(1).replace(",", ""))

    desc_el = soup.select_one('p.explanation[itemprop="description"]')
    description_text = desc_el.get_text() if desc_el else ""

    return build_record(url, title, description_text, price)


def scrape_category_list_page(category_url: str) -> list[dict]:
    soup = fetch_page(category_url)
    items = soup.select("li.column")

    results = []
    for item in items:
        link_el = item.select_one('a[href*="/items/"]')
        title_el = item.select_one("h2.show_on_hover")
        price_el = item.select_one("div.item-detail div.price")
        if not link_el or not title_el:
            continue

        title = title_el.get_text(strip=True)
        product_url = link_el.get("href", "")

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        results.append({"raw_name": title, "product_url": product_url, "price": price})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = {}
    for category_url in LIST_CATEGORY_URLS:
        for item in scrape_category_list_page(category_url):
            all_list_items[item["product_url"]] = item
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items.values():
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"], price=item.get("price")):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

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
        with open("data_nagi.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_nagi.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
