# -*- coding: utf-8 -*-
"""
scrape_iriya.py

入谷珈琲豆店(iriyacoffee.shopselect.net、東京都台東区入谷)の商品情報を
取得する。BASEのカスタムドメイン(shopselect.net)。

【JSON-LD Productが存在しない点について】
実データ確認済み: FIVE COFFEE STAND&ROASTERYと同じBASEテーマで、
`application/ld+json`のProduct構造化データを出力しない。代わりに
`window.dataLayer.push({...})`に`item_name`・`itemPrice`・
`item_purchasability`が埋め込まれている。正規表現で個別フィールドを
抽出する。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【同一銘柄が焙煎度違いで複数商品として掲載される点について】
実データ確認済み: 同じ産地銘柄が「／浅煎り」「／中煎り」「／深煎り」で
別商品(別URL)として個別に掲載されている(焙煎度選択式ではない)ほか、
ブレンド名を冠した「”だけ”ブレンド」という単一農園を強調した商品名も
別途存在する。いずれも商品名に焙煎度・産地が含まれ、parse_product()の
既存のROAST_KEYWORDS判定でカバーされるため、特別な処理は不要。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上43件、うちhome/about除く41件が商品):
「初心者セット［送料無料］」(福袋的なセット商品)、「コーヒー保存缶」
(器具)、「かんたんドリップ　30枚入」(フィルター器具)がコーヒー豆単品
ではないためNON_BEAN_KEYWORDSで除外する。残りは単一銘柄・ブレンドの
焙煎豆(100g/200g)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "入谷珈琲豆店",
    "url": "https://iriyacoffee.shopselect.net/",
    "platform": "BASE",
    "address": "東京都台東区入谷1-19-6",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://iriyacoffee.shopselect.net"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["初心者セット", "保存缶", "かんたんドリップ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
NAME_PATTERN = re.compile(r"'item_name':\s*\"((?:[^\"\\]|\\.)*)\"")
PRICE_PATTERN = re.compile(r"'itemPrice':\s*(\d+)")
PURCHASABILITY_PATTERN = re.compile(r"'item_purchasability':\s*\"([^\"]*)\"")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_datalayer_fields(html: str) -> dict | None:
    name_m = NAME_PATTERN.search(html)
    if not name_m:
        return None
    title = json.loads(f'"{name_m.group(1)}"')
    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html)
    purchasability = purchasability_m.group(1) if purchasability_m else ""
    return {"title": title, "price": price, "purchasability": purchasability}


def build_record(product_url: str, fields: dict) -> dict | None:
    title = fields["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": fields["price"],
            "product_url": product_url,
        }

    structural_out_of_stock = fields["purchasability"] != "purchasable"
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
        "price": fields["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    fields = extract_datalayer_fields(fetch_html(url))
    if not fields:
        return None
    return build_record(url, fields)


def fetch_sitemap_urls() -> list[str]:
    html = fetch_html(f"{BASE_URL}/sitemap.xml")
    soup = BeautifulSoup(html, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_datalayer_fields(fetch_html(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if not fields:
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record(product_url, fields)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
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
        with open("data_iriya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_iriya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
