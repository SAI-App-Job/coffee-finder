# -*- coding: utf-8 -*-
"""
scrape_cafeviola.py

Cafe Viola(カフェビオラ、cafeviola.official.ec、〒882-0051 宮崎県延岡市
富美山町83-421、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE
(official.ecドメイン。他のBASE系店舗と同一のrobots.txt・OGP構造)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
特定商取引法ページ(https://cafeviola.official.ec/law)で実データ確認済み
(2026-09時点): 事業者名「宇野賢二」、所在地「〒882-0051 宮崎県延岡市富美山町
83-421」との記載を確認。候補リストの住所と一致。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。
sitemap.xmlの/items/配下に全5件。

【対象商品について】
実データ確認済み(全5件): 「DRIP BAG COFFEE」(ドリップバッグ、1件)を除く
4件が単一銘柄のコーヒー豆(マンデリン・エチオピアゲイシャ・エチオピア
イルガチェフェ・「TEZUMI KANJUKU」手摘み完熟)で、重量違いの重複は無い
(各銘柄1種類の重量のみ)。NON_BEAN_KEYWORDSで除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Cafe Viola",
    "url": "https://cafeviola.official.ec/",
    "platform": "BASE",
    "address": "宮崎県延岡市富美山町83-421",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cafeviola.official.ec"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["DRIP BAG"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[（(]\s*\d+\s*[gｇ]\s*[）)]\s*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(title: str, price: int | None, product_url: str) -> dict | None:
    base_name, weight_g = base_name_and_weight(title)
    if not base_name:
        return None
    parsed = parse_product(base_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(base_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
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
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        detail = build_record(title, fields["price"], product_url)
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
    with open("data_cafeviola.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafeviola.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
