# -*- coding: utf-8 -*-
"""
scrape_sabucoffee.py

株式会社サブ珈琲(sabucoffee.raku-uru.jp、高知県高知市南竹島町39-9、
自家焙煎豆のオンライン販売)の商品情報を取得する。楽々シリーズ
(Raku-Uru)。scrape_kogetsuan.pyと同一プラットフォーム。

【住所について】
実データ確認済み(2026-09時点): 公式ストアの特定商取引法ページ
(https://sabucoffee.raku-uru.jp/law)で「〒780-8017 高知市南竹島町
39-9」と一致確認済み。

robots.txt確認済み(2026-09時点): /robots.txtは標準的なRaku-Uru設定で、
本スクレイパーが使う一覧・詳細ページは制限対象外。

【カテゴリ構造と重複について】
実データ確認済み: 「ブレンドコーヒー」(categoryId=90842)に5銘柄
(プレミアムビター・オリジナルブレンド・ノーブルブレンド・クラシック
ブレンド・土佐備長炭炭焼珈琲、いずれも200g)が登録されている。別カテゴリ
「ポスト投函発送専用」(categoryId=93850)には同じ5銘柄の「ポスト投函専用」
版(郵便受け投函配送に最適化した同一商品の再登録)が並行して存在するため、
重複を避けて「ブレンドコーヒー」カテゴリのみを対象とする。「ギフト」
(categoryId=95101、1件)はギフトセットのため対象外。

【在庫状況について】
実データ確認済み: 香月庵と同じ構造化フラグ(a.raku-add-cart の有無、
div.item-dtail-orderinvalid の有無)で在庫判定できる。

【重量について】
実データ確認済み: 全5件とも商品名末尾に「200ｇ」を含む固定重量。
香月庵と異なり商品詳細ページのフッター欄に「内容量」表記が無いため、
商品名からのみ重量を取得する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "サブ珈琲",
    "url": "https://sabucoffee.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "高知県高知市南竹島町39-9",
    "prefecture": "高知県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なRaku-Uru設定で、"
                          "本スクレイパーが使う一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://sabucoffee.raku-uru.jp"
# 理由はモジュールdocstring参照(「ポスト投函発送専用」カテゴリは同一商品の
# 重複のため対象外、「ギフト」もセット品のため対象外)
BEAN_CATEGORY_ID = "90842"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_ids() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/item-list?categoryId={BEAN_CATEGORY_ID}")
    ids = []
    for a in soup.select('p.item-name a[href^="/item-detail/"]'):
        href = a.get("href", "")
        item_id = href.rsplit("/", 1)[-1]
        if item_id and item_id not in ids:
            ids.append(item_id)
    return ids


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one("div.item-head h1.title1")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title:
        return None

    price_el = soup.select_one("b.raku-item-vari-price-num")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    has_orderinvalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    has_add_cart = soup.select_one("a.raku-add-cart") is not None
    structural_out_of_stock = has_orderinvalid and not has_add_cart
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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_ids = fetch_item_ids()

    records = []
    flavored_records = []
    for item_id in item_ids:
        product_url = f"{BASE_URL}/item-detail/{item_id}"
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_sabucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sabucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
