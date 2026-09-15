# -*- coding: utf-8 -*-
"""
scrape_atticcoffee.py

出島珈琲焙煎所(Attic Coffee、atticcoffee.theshop.jp、〒850-0862
長崎県長崎市出島町1-1 長崎出島ワーフ1F、自家焙煎豆専門店)の商品情報を
取得する。THE SHOP(BASE系)。

robots.txt確認済み(2026-09時点): こやまこおふぃ・NAGI COFFEE・珈琲家
あのころ等と同一の記述(curl/python-requests等の一般的なHTTPクライアント
は個別にDisallow: /指定があるが、User-agent: *ルールでは/cart/・
/shops/・違反報告ページ以外はAllow: /)。本スクレイパーが使う商品詳細
ページ(/items/)とカテゴリ一覧ページ(/categories/)はいずれもDisallow
対象に含まれない。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「コーヒー豆」(id=969414)カテゴリに
4件、うち3件が銘柄ブレンド(長崎ブレンド/出島ブレンド/龍馬ブレンド)で
1件が「【お試しコーヒーメール便】ブレンド２種類セット」という複数
ブレンドの詰め合わせのため対象外。NON_BEAN_KEYWORDSで除外する。他の
カテゴリ(季節のギフト・ギフト・コーヒーテトラ・オリジナル商品・
アウトドア・トラベル・コーヒー器具)はいずれも非対象。

【産地・品種情報について】
実データ確認済み: 3件のブレンドはいずれも産地内訳(配合比率等)の記載が
無いため、origin_country/blend_componentsは空(null/[])のままにする。

【重量について】
実データ確認済み: 商品名に重量表記が無い。詳細ページのdescriptionにも
構造化された内容量欄が見つからなかったため、weight_gはnullとする。
"""

import json
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "出島珈琲焙煎所",
    "url": "https://atticcoffee.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "長崎県長崎市出島町1-1 長崎出島ワーフ1F",
    "prefecture": "長崎県",
    "robots_txt_status": "実質許可(2026-09確認。こやまこおふぃ・NAGI COFFEE等と同一の記述。"
                          "/cart/・/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://atticcoffee.theshop.jp"
CATEGORY_ID = "969414"  # コーヒー豆(理由はモジュールdocstring参照)
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]


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
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") else None
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
        "weight_g": None,
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


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{CATEGORY_ID}")
    results = []
    seen_urls = set()
    for link_el in soup.select('a[href*="/items/"]'):
        title_el = link_el.select_one('[class*="itemTitleText"]')
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = scrape_category_list()

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        try:
            detail = parse_product_detail(item["product_url"])
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
        with open("data_atticcoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_atticcoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
