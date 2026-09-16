# -*- coding: utf-8 -*-
"""
scrape_sakuraicoffee.py

室蘭桜井珈琲(sakuraicoffe.shop34.makeshop.jp、北海道室蘭市中島町3丁目
13-14、MakeShop)の商品情報を取得する。

住所は特定商取引法ページ(https://sakuraicoffe.shop34.makeshop.jp/view/contract)
で実データ確認済み(2026-09時点、北海道室蘭市中島町3丁目13-14(さはら病院向い))。

【対象カテゴリについて】
実データ確認済み: 「■珈琲豆一覧(焙煎別)」(ct26)が全銘柄を横断的に一覧
表示するカテゴリで、全25件がこの1ページに収まる(ページネーション無し)。
このうち「水出しｱｲｽｺｰﾋｰ（40g×4袋）」(コールドブリューパック)と
「ドリップコーヒー/◯◯ブレンド」4件(個包装ドリップ)は非対象のため
NON_BEAN_KEYWORDSで除外し、残り20件が単一銘柄の200gコーヒー豆。

【一覧ページのみで完結する点について】
実データ確認済み: 一覧ページのli要素にp.item-name(商品名+リンク)・
p.price(価格)が揃っているため、詳細ページへの追加アクセスは行わない。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404、独自404
ページが返る)。制限の明示的な記述が無いため実質許可とみなす。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "室蘭桜井珈琲",
    "url": "https://sakuraicoffe.shop34.makeshop.jp/",
    "platform": "MakeShop",
    "address": "北海道室蘭市中島町3丁目13-14",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-09確認。robots.txt自体が存在しない"
                          "=404で独自404ページが返る。制限の明示的な記述なし)",
}

BASE_URL = "https://sakuraicoffe.shop34.makeshop.jp"
LIST_URL = f"{BASE_URL}/view/category/ct26"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出し", "ドリップコーヒー"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def build_record(a_el) -> dict | None:
    title = a_el.get_text(strip=True)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    href = a_el.get("href", "")
    product_url = f"{BASE_URL}{href}" if href.startswith("/") else href

    li = a_el.find_parent("li")
    price = None
    if li:
        price_el = li.select_one("p.price")
        if price_el:
            m = re.search(r"[\d,]+", price_el.get_text())
            if m:
                price = int(m.group().replace(",", ""))

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
    soup = fetch_page(LIST_URL)

    records = []
    flavored_records = []
    for a_el in soup.select("p.item-name a"):
        detail = build_record(a_el)
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
    with open("data_sakuraicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sakuraicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
