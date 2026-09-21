# -*- coding: utf-8 -*-
"""
scrape_sapporomikazuki.py

自家焙煎珈琲豆工房 札幌三日月(sapporomikazuki.com、札幌市南区石山東6丁目
2-1、Jimdo)の商品情報を取得する。本プロジェクトで初めて対応するJimdo
「ネットショップ」ネイティブ機能(茶果/CLAXON等の外部カート連携型Jimdoとは
異なり、Jimdo自体のショップ機能を使用)。

住所は/about/ページで実データ確認済み(2026-09時点、株式会社トヨケン
北海道札幌市南区石山東6丁目2-1)。

【商品情報の取得方法について】
実データ確認済み: 「オンラインストア」ページ(/ネットショップ/)にschema.org
の構造化マークアップ(itemprop)で全11件の商品が1ページに収まっている。
商品名はh4.fn[itemprop="name"]、価格はp[itemprop="price"]のcontent属性、
在庫状況はmeta[itemprop="availability"]のcontent値(InStock/OutOfStock)。
ページネーションは無い(実データ確認済み、全11件が1ページに表示)。

【重量表記について】
実データ確認済み: 商品名の多くに「200ℊ」との表記があるが、この「ℊ」は
Unicode書法用小文字G(U+210A SCRIPT SMALL G)であり、半角/全角の「g」
「ｇ」とは異なるコードポイント。重量抽出の正規表現にこの文字も含める。

【対象商品について】
実データ確認済み(全11件): 全件が単一銘柄のブレンド/ストレートのコーヒー豆
(200g)で、非対象商品(器具・グッズ等)は無かった。

【flavor_notes(2026-09-21追記)】
実データ確認済み: div.description[itemprop="description"]にテイスティング
文が直接入っている(対象11件全て確認)。価格・スペック等の混入は無い
ため全文をそのまま採用する。

robots.txt確認済み(2026-09時点): User-agent: *は/app/と/j/を制限するが、
本スクレイパーが使う/ネットショップ/ページ自体・および商品情報が構造化
されているHTMLは制限対象外(/app/module/webproduct/goto/のみ個別にAllow
指定あり、これは商品購入導線の別ページであり本スクレイパーは使用しない)。
Crawl-Delay: 5指定に従う。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎珈琲豆工房 札幌三日月",
    "url": "https://www.sapporomikazuki.com/",
    "platform": "Jimdo",
    "address": "北海道札幌市南区石山東6丁目2-1",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *は/app/と/j/を制限するが、"
                          "本スクレイパーが使うページは制限対象外。Crawl-Delay: 5に従う)",
}

SHOP_PAGE_URL = "https://www.sapporomikazuki.com/%E3%83%8D%E3%83%83%E3%83%88%E3%82%B7%E3%83%A7%E3%83%83%E3%83%97/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(U+210A SCRIPT SMALL G。半角g・全角ｇも念のため許容)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇℊ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def build_record(product_el) -> dict | None:
    name_el = product_el.select_one('h4.fn[itemprop="name"]')
    if not name_el:
        return None
    title = name_el.get_text(strip=True)

    desc_el = product_el.select_one('div.description[itemprop="description"]')
    flavor_notes = desc_el.get_text(" ", strip=True) if desc_el else None
    flavor_notes = flavor_notes or None

    price_el = product_el.select_one('[itemprop="offers"] [itemprop="price"]')
    price = None
    if price_el and price_el.get("content"):
        try:
            price = int(float(price_el["content"]))
        except (TypeError, ValueError):
            price = None

    availability_el = product_el.select_one('[itemprop="offers"] meta[itemprop="availability"]')
    availability = (availability_el.get("content") if availability_el else "") or ""
    structural_out_of_stock = availability != "InStock"

    url_el = product_el.select_one('[itemprop="offers"] meta[itemprop="url"]')
    product_url = url_el.get("content") if url_el else None

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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    soup = fetch_page(SHOP_PAGE_URL)

    records = []
    flavored_records = []
    for product_el in soup.select('div[id^="product-desc-"]'):
        detail = build_record(product_el)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_sapporomikazuki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sapporomikazuki.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
