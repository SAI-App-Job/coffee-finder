# -*- coding: utf-8 -*-
"""
scrape_roast227.py

焙煎香房227(roast227.thebase.in、〒870-1168 大分県大分市上宗方南1丁目1-6、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(thebase.inドメイン)。

【店舗・ネットショップについて】
実データ確認済み(2026-09時点): 公式サイトroast-227.comの「ネットショップ」
ページには「焙煎香房227 BASE店」と「焙煎香房227 STORES店」の2つのリンクが
掲載されているが、本プロジェクトの方針によりSTORES.jp店は対象外とし、
BASE店(roast227.thebase.in)のみを対象とする。

【住所について】
特定商取引法ページ(https://roast227.thebase.in/law)で実データ確認済み
(2026-09時点): 事業者の名称「焙煎香房227 田北文弘」、事業者の所在地
「〒870-1168 大分県大分市上宗方南1-1-6」との記載を確認。公式サイトの
店舗情報ページ(roast-227.com/about/)の住所とも一致し、候補リストの住所と
一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(全10件): sitemap.xmlの/items/配下10件のうち、実際の焙煎豆
単品(200g)は6件(インドネシアセレベスアラビカ・トミオフクダDOT・
エメラルドマウンテン・エチオピアモカ・グアテマラデカフェ・
ルワンダスカイヒル)。他は水出し珈琲パック・おためし4種パック(詰め合わせ)・
ドリップパック10パックセット・コーヒーシューラスク(菓子)のため非対象。
NON_BEAN_KEYWORDSで除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "焙煎香房227",
    "url": "https://roast227.thebase.in/",
    "platform": "BASE",
    "address": "大分県大分市上宗方南1丁目1-6",
    "prefecture": "大分県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://roast227.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出し", "おためし", "ドリップパック", "シューラスク", "パック"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇℊ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*[（(]?\s*\d+\s*[gｇℊ]\s*[）)]?\s*$")


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
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    if not WEIGHT_PATTERN.search(title):
        return None
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
        detail = build_record(fields["title"], fields["price"], product_url)
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
    with open("data_roast227.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roast227.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
