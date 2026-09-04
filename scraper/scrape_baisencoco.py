# -*- coding: utf-8 -*-
"""
scrape_baisencoco.py

自家焙煎 香珈 Beans＆Cafe(baisen-coco.com、千葉県、カフェ併設の自家
焙煎豆販売)の商品情報を取得する。Goope(グーペ)、このプロジェクト初
対応のプラットフォーム。カフェのメニューシステム(/menu)を使って
豆売り商品も掲載している。

robots.txt確認済み(2026-09時点): `User-agent: * / Allow: /`、制限なし。

【カテゴリ構造について】
実データ確認済み: 全9メニューカテゴリ(テイクアウト・ドリンク・フード・
珈琲豆／ブレンド・珈琲豆／アフリカ・珈琲豆／南米・珈琲豆／中米・
珈琲豆／その他・珈琲豆／お手軽)のうち、「珈琲豆／」で始まる6カテゴリ
(計16件)のみが豆売り商品を指す。「珈琲豆／お手軽」内の「ドリップ
バック珈琲」(1件)は豆単品ではなくドリップバッグの受注生産のため
NON_BEAN_KEYWORDSで除外し、残り15件が対象。

【重量について】
実データ確認済み: 15件中9件は商品名に「（100g）」と明記されている一方、
比較的新しく追加されたと見られる6件(モカ　ナチュラルフルーツ／
マラウイ　フィリルア　ゲイシャ／コロンビア　スプレモ　ナリーニョ／
コスタリカ　SHB コーラルマウンテン／バリ島　シガラジャ　ブルームーン／
インド　モンスーン)には重量表記が無く、商品詳細ページ(個別の
menu_bodyの説明文)にも重量の記載が見つからなかった。未確認の数値を
推測で補完せず、これらはweight_g=Noneのままとする。

【価格について】
実データ確認済み: 一部商品は「780 円～」のように「～」(以上)付きの
表記があるが、他の店舗と同様、この基準価格(先頭の数値)をそのまま
採用する。

【在庫・販売状況について】
実データ確認済み: カフェメニューシステムのため在庫フラグの概念が
無く、構造化された品切れ表示は見つからなかった。商品名テキストのみで
判定する(detect_stock_status())。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎 香珈 Beans＆Cafe",
    "url": "https://baisen-coco.com/",
    "platform": "Goope",
    "address": "千葉県",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-09確認。User-agent: * / Allow: /、制限なし)",
}

BASE_URL = "https://baisen-coco.com"
MENU_URL = f"{BASE_URL}/menu"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BEAN_CATEGORY_PREFIX = "珈琲豆／"
NON_BEAN_KEYWORDS = ["ドリップバック", "ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_bean_items() -> list[dict]:
    soup = fetch_page(MENU_URL)
    results = []
    current_category = None
    for el in soup.select("div.menu_category, div.menu"):
        if "menu_category" in (el.get("class") or []):
            span = el.select_one("span")
            current_category = span.get_text(strip=True) if span else None
            continue
        if not current_category or not current_category.startswith(BEAN_CATEGORY_PREFIX):
            continue

        title_el = el.select_one("div.menu_title a")
        price_el = el.select_one("div.menu_price")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        product_url = title_el.get("href", "")
        if product_url and not product_url.startswith("http"):
            product_url = f"{BASE_URL}{product_url}"

        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        results.append({"raw_name": title, "product_url": product_url, "price": price})
    return results


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
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
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title)
    weight_match = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_match.group(1)) if weight_match else None

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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_bean_items()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            continue
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"], price=item.get("price")):
            records.append(prev)
            continue

        detail = build_record(item)
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
    with open("data_baisencoco.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisencoco.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
