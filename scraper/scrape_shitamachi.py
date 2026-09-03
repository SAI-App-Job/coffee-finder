# -*- coding: utf-8 -*-
"""
scrape_shitamachi.py

下町コーヒー(shitamachicoffee.com、東京都大田区南六郷)の商品情報を取得する。
独自EC基盤(xaas3.jp、複数の関東の店舗で見られるカートシステム)。

robots.txt確認済み(2026-09時点、https://www.shitamachicoffee.com/robots.txt):
/default/error/・/preview/のみDisallow。それ以外は制限なし。
「shitamachicoffee.com」(wwwなし)は301で「www.shitamachicoffee.com」へ
リダイレクトされるため、リクエストはwww付きドメインに対して行う。

【商品一覧ページの情報が古い点について】
実データ確認済み: /product.htmlという紹介ページに「ブレンド」2件+
「シングルオリジン」12件、計14件の商品名・商品コード(a001〜a023)が
静的に列挙されているが、実際に/item/aXXX/へアクセスすると6件
(a001/a006/a008/a013/a017/a022)のみが実在の商品ページ(タイトル・価格
あり)で、残り8件(a005/a009/a010/a016/a019/a020/a021/a023)は販売終了に
なったと見られ空の商品詳細ページ(タイトル・価格情報なし)が返ってくる。
そのため商品コード候補リストをdiscovery用として使い、詳細ページの
タイトルが取得できたものだけを収録する(取得できない場合は静かに
スキップする、という設計)。

【重量について】
実データ確認済み: 全商品が「生豆(焙煎前)の状態で200gを基準に計量」
かつ「煎り上がり(焙煎後)は約170g前後」という表記。この
プロジェクトが対象とする実際に販売される焙煎豆の重量として、
「仕上がり約Ng」という焙煎後の重量を優先的に抽出する
(見つからない場合のみ商品名の最初の重量表記にフォールバック)。

【在庫について】
実データ確認済み: 一覧・詳細ページのどちらにも構造化された品切れ表示
要素が見当たらないため、商品名のテキストのみで在庫状態を判定する。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "下町コーヒー",
    "url": "https://www.shitamachicoffee.com/",
    "platform": "独自EC(xaas3.jp)",
    "address": "東京都大田区南六郷",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/・/preview/のみDisallow、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.shitamachicoffee.com"
# 理由はモジュールdocstring参照(/product.htmlに列挙された全商品コード。
# 実在しないものは詳細ページ取得時に静かにスキップされる)
CANDIDATE_ITEM_CODES = [
    "a001", "a005", "a006", "a008", "a009", "a010", "a013",
    "a016", "a017", "a019", "a020", "a021", "a022", "a023",
]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TITLE_PATTERN = re.compile(r'<div id="itemDetail01"[^>]*>\s*<h2>([^<]*)</h2>')
PRICE_PATTERN = re.compile(r'sales_price">[\s\S]{0,300}?<span>([\d,]+)円')
ROASTED_WEIGHT_PATTERN = re.compile(r"仕上がり約(\d+)\s*[gｇ]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def build_record(product_url: str, title: str, price: int | None) -> dict:
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

    stock_status = detect_stock_status(title)

    weight_m = ROASTED_WEIGHT_PATTERN.search(title) or WEIGHT_PATTERN.search(title)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    html = fetch_html(url)
    title_m = TITLE_PATTERN.search(html)
    if not title_m:
        return None
    title = title_m.group(1).strip()
    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1).replace(",", "")) if price_m else None
    return build_record(url, title, price)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for code in CANDIDATE_ITEM_CODES:
        product_url = f"{BASE_URL}/item/{code}/"
        try:
            html = fetch_html(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_m = TITLE_PATTERN.search(html)
        if not title_m:
            continue
        title = title_m.group(1).strip()

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        price_m = PRICE_PATTERN.search(html)
        price = int(price_m.group(1).replace(",", "")) if price_m else None
        detail = build_record(product_url, title, price)
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = parse_product_detail(url)
        print(result)
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        import json
        with open("data_shitamachi.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_shitamachi.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
