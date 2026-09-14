# -*- coding: utf-8 -*-
"""
scrape_bankokucoffee.py

ばんこく珈琲 津山(shop.bankoku-coffee.jp、〒708-0824 岡山県津山市沼10丁目
5番、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【住所について】
特定商取引法ページ(https://shop.bankoku-coffee.jp/law)を実データ確認し、
候補リストの住所と一致することを確認した(2026-09時点、運営会社「有限
会社ばんこく津山」)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品構成について】
実データ確認済み(sitemap.xml全43件): コーヒー豆単品17銘柄(各種ブレンド・
シングルオリジン、いずれも200g、一部100g)と、非対象の「水出しコーヒー
(小)3個パック」(産地非依存の詰め合わせ)、「ばんこくオリジナル(コーヒー)
ギフト」各種、「1日のルーティン」「ばんこく焙煎人おすすめ3種」「はじめて
のばんこく珈琲３種お試し」各セット(複数銘柄詰め合わせ)、「津山榕菴珈琲
ドリップバッグ」各種、「津山榕菴珈琲 清流 木箱100g×3」(木箱ギフト)、
「ばんこくを旅する定期便」各種(定期購入)、「ギフトボックス」(包装材)、
「コーヒー焙煎機で煎ったアーモンド」(コーヒー豆ではない)、「コーヒー豆
保存缶」(器具)、「豊島エスポワールパーク様専用」(特定法人向け専用OEM
商品、一般販売商品ではないため非対象)。NON_BEAN_KEYWORDSで除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ばんこく珈琲 津山",
    "url": "https://shop.bankoku-coffee.jp/",
    "platform": "BASE",
    "address": "岡山県津山市沼10丁目5番",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.bankoku-coffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    # 「セット」は「サンセットブレンド」のような正規商品名の部分文字列に
    # 誤爆するため、単独の「セット」ではなく具体的なセット商品名の断片
    # (「ルーティン」「おすすめ3種」「お試しセット」)で除外する
    "水出しコーヒー", "ギフト", "ルーティン", "おすすめ3種", "お試しセット",
    "ドリップバッグ", "木箱", "定期便", "アーモンド", "保存缶", "様専用",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    title = re.sub(r"\s+", " ", title)
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for product_url in item_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        detail = build_record({**fields, "url": product_url})
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
    with open("data_bankokucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bankokucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
