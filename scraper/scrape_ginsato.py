# -*- coding: utf-8 -*-
"""
scrape_ginsato.py

徳島焙煎工房(gin-sato.jp内の「コーヒー～徳島焙煎工房～」カテゴリで販売、
徳島県徳島市南田宮2丁目2-46、自家焙煎豆のオンライン販売)の商品情報を
取得する。株式会社のびる(novil.co.jp)が運営する食品モール「吟のさと」
(ShopServeプラットフォーム)にテナント出店する形態。本プロジェクトで
初めて対応するShopServe。

【店舗の特殊性について】
実データ確認済み(2026-09時点): 徳島焙煎工房自体は自社の通販サイトを持たず、
親会社(株式会社のびる)が運営する食品モール「吟のさと」(gin-sato.jp)内の
専用カテゴリ(/SHOP/269331/list.html)でのみ販売している。同社の店舗紹介
ページ(https://www.novil.co.jp/baisen-koubou/)に「徳島焙煎工房 田宮店
徳島県徳島市南田宮2丁目2-46」との記載があり、候補リストの住所と一致する
ことを確認済み(一次情報)。

robots.txt確認済み(2026-09時点): gin-sato.jpのrobots.txtは一般的な
ShopServe標準設定で、本スクレイパーが使う商品ページ・カテゴリページは
制限対象外。

【商品構成について】
実データ確認済み: 専用カテゴリには「【徳島焙煎工房】レギュラー珈琲
200g」(/SHOP/coffee.html、800円)と「【ゆうパケット送料無料】【お試し】
徳島焙煎工房オリジナルブレンド 200g」(/SHOP/coffee_200.html、1080円)の
2商品のみが登録されている。両者は商品名・重量(200g)は同一で、後者は
郵便受け投函配送(ゆうパケット)を前提に送料込みで価格を引き上げた同一
商品のバリエーションであることを商品説明で確認済み(実質的に同一の
オリジナルブレンド200gを指す)。重複を避けるため、送料込み価格ではない
通常版(/SHOP/coffee.html)のみを対象とする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "徳島焙煎工房",
    "url": "https://gin-sato.jp/SHOP/269331/list.html",
    "platform": "ShopServe(吟のさと内テナント出店)",
    "address": "徳島県徳島市南田宮2丁目2-46",
    "prefecture": "徳島県",
    "robots_txt_status": "実質許可(2026-09確認。ShopServe標準のrobots.txtで、"
                          "本スクレイパーが使う商品ページ・カテゴリページは"
                          "制限対象外)",
}

REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
# 理由はモジュールdocstring参照(送料込みの「お試し」版は同一商品の重複の
# ため対象外とし、通常版のみをハードコードで指定する)
PRODUCT_URL = "https://gin-sato.jp/SHOP/coffee.html"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    # 理由: このテーマは空のh1(レイアウト用)と商品名を持つh1が併存するため、
    # 空でない最初のh1を採用する(実データ確認済み)
    title = ""
    for h1_el in soup.select("h1"):
        text = h1_el.get_text(strip=True)
        if text:
            title = text
            break
    if not title:
        return None

    price_el = soup.select_one("span.selling_price")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    try:
        detail = build_record(fetch_page(PRODUCT_URL), PRODUCT_URL)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {PRODUCT_URL} ({e})")
        return [], []

    if detail is None:
        return [], []
    if detail.get("is_flavored"):
        return [], [detail]
    return [detail], []


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_ginsato.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ginsato.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
