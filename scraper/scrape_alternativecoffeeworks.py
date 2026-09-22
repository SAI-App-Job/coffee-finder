# -*- coding: utf-8 -*-
"""
scrape_alternativecoffeeworks.py

Alternative Coffee Works(acw2019.thebase.in、東京都新宿区北新宿4-3-1、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
高田馬場・早稲田エリアの自家焙煎コーヒー豆店が本アプリに1件も収録されて
いないという利用者からの指摘を受けた総点検で発見(tailoredcafe.jpの
「高田馬場・早稲田のコーヒー豆おすすめ専門店10選」記事経由。同記事では
大久保駅最寄りとして紹介されている)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品構成について】
実データ確認済み(sitemap.xml全4件、2026-09時点): コーヒー豆単品2銘柄
(オルタナティブ・ブレンド(ミディアムロースト)・グランジ・ブレンド
(ダークロースト)、いずれも100g)と、非対象の「ドリップバッグ(5個)」
(個包装の挽いた豆で単品の焙煎豆売りとは形態が異なる)・「カスカラシロップ」
(コーヒーチェリーの果皮を使ったシロップで焙煎豆ではない)。
NON_BEAN_KEYWORDSで除外する。

【flavor_notes】
実データ確認済み: 対象2件ともog:descriptionは「賞味期限は焙煎日より
1ヶ月以内が美味しい期限です。すぐに飲まない場合は冷凍保存をオススメ
します。」という保存方法の定型文のみで、風味・テイスティングに関する
記述が一切無い(ページ本文も同内容)。存在しない情報を創作しないため、
flavor_notesはnullのままとする。

【焙煎度について】
商品名に括弧書きで焙煎度が明記されている(「(ミディアムロースト)」
「(ダークロースト)」)。「ミディアムロースト」はcoffee_parser.py内の
ROAST_KEYWORDSで検出されるが、「ダークロースト」は同キーワード集に
無いため検出されずroast_level=Noneとなる(該当キーワードが無い場合に
独自マッピングを追加すると他店舗への影響範囲が広がるため、本スクレイパー
では対応せずNoneのまま許容する)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Alternative Coffee Works",
    "url": "https://acw2019.thebase.in/",
    "platform": "BASE",
    "address": "東京都新宿区北新宿4-3-1",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://acw2019.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "シロップ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {"title": title, "price": price, "weight_g": weight_g}


def build_record(item: dict) -> dict | None:
    title = item["title"].strip()
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
        "flavor_notes": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        fields = extract_fields(soup)
        if not fields:
            continue
        all_items.append({**fields, "url": product_url})

    records = []
    flavored_records = []
    for item in all_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_alternativecoffeeworks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_alternativecoffeeworks.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
