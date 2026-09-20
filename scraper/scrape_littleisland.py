# -*- coding: utf-8 -*-
"""
scrape_littleisland.py

自家焙煎工房カフェ littleisland(littleisland.shop、大阪府大阪狭山市狭山
2-944-1〈狭山本店/自社焙煎拠点〉、自家焙煎豆のオンライン販売)の商品情報を
取得する。WordPress+WooCommerce。公開Store API(/wp-json/wc/store/products、
バージョン無しの旧Blocks系エンドポイント。/wp-json/wc/store/v1/productsは
存在しないためこちらを使用)から認証不要で取得する。

住所は自社サイトの店舗案内ページ(https://littleisland.shop/about )で確認済み。
「大阪・狭山市の自家焙煎工房カフェ littleisland狭山本店を拠点とし」「店舗名
（1）自家焙煎工房カフェ littleisland 狭山本店」「住所（1）大阪府大阪狭山市
狭山2-944-1」との記載があり、狭山本店が自家焙煎の拠点。他に堺市南区三原台の
菓子工房・大阪狭山市池尻中の狭山池博物館内店舗があるが、いずれも焙煎拠点では
ないため狭山本店の住所を採用する。

robots.txt確認済み(2026-09時点): WordPress標準robots.txt(/wp-admin/のみ
Disallow、admin-ajax.phpはAllow)で実質許可。

【商品バリエーション(重量)の取得方法について】
実データ確認済み: 全24件のコーヒー豆商品はいずれもWooCommerceの可変商品
(has_options: true)で、「100g-粉」「100g-豆」「250g-粉」「250g　豆」の
4バリエーション(挽き方違いは同一価格)を持つ。Store APIのprices.price_range
のmin_amountが常に100gバリエーションの価格と一致することを複数商品の商品
ページ(data-product_variations属性のJSON)で実データ確認済みのため、商品
詳細ページへの個別アクセスを行わずmin_amountを100gの代表価格として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み(Store API上全25件): 「オリジナルドリップパック」
(単一価格の固定商品、has_options: false)が非対象。NON_BEAN_KEYWORDSで
除外する。残り24件が豆単品(いずれも100g/250gの2サイズ展開)。

【flavor_notes(2026-09-20追記)】
実データ確認済み: Store APIのdescriptionフィールドは全商品で空文字列
(構造化商品情報はテーマ独自のdl.c-detail-dataというアコーディオンUIで
商品詳細ページ側にのみレンダリングされる)。そのため商品詳細ページ
(permalink)を個別取得し、dl.c-detail-data内の見出し「商品説明」に
対応するdd要素をflavor_notesとして採用する(続く「商品規格」「備考」の
dd要素は産地スペック・☆評価のみでテイスティング文を含まないため対象
外)。「商品説明」のdd要素はテイスティング文に続けて農園の背景説明も
含むが、既存の他店舗と同様に背景説明も含めて採用する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎工房カフェ littleisland",
    "url": "https://littleisland.shop/",
    "platform": "WooCommerce",
    "address": "大阪府大阪狭山市狭山2-944-1",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。WordPress標準robots.txt、"
                          "/wp-admin/のみDisallow)",
}

API_URL = "https://littleisland.shop/wp-json/wc/store/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップパック"]
CRAWL_DELAY_SECONDS = 1


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(product_url: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not product_url:
        return None
    try:
        soup = fetch_page(product_url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
        return None
    dl = soup.select_one("dl.c-detail-data")
    if not dl:
        return None
    for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
        if "商品説明" in dt.get_text():
            text = dd.get_text(" ", strip=True)
            return text or None
    return None


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def build_record(product: dict) -> dict | None:
    name = (product.get("name") or "").strip()
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(name)
    prices = product.get("prices") or {}
    if product.get("has_options") and prices.get("price_range"):
        price_raw = prices["price_range"].get("min_amount")
    else:
        price_raw = prices.get("price")
    price = int(price_raw) if price_raw is not None else None
    product_url = product.get("permalink")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = not product.get("is_in_stock", True)
    stock_status = detect_stock_status(name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": extract_flavor_notes(product_url),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        # 可変商品の最小バリエーションは常に100g(docstring参照)
        "weight_g": 100 if product.get("has_options") else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_littleisland.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_littleisland.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
