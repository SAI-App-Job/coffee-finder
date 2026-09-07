# -*- coding: utf-8 -*-
"""
scrape_sakuramame.py

さくら珈琲豆店(sakura-mame.ocnk.net、愛知県名古屋市北区金城町2丁目
29-3、自家焙煎豆(有機栽培コーヒー中心)のオンライン販売)の商品情報を
取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【商品一覧の取得方法について】
実データ確認済み: 「有機栽培珈琲：ストレート」(product-list/2、7件)と
「有機栽培珈琲：ブレンド」(product-list/20、5件)の2カテゴリで焙煎豆単品
の全11件を網羅できる(中煎り豆/深煎り豆カテゴリはこの2つの焙煎度別
サブセットのため重複、巡回不要)。「ネット限定／送料無料セット」
「ギフトセット」「業務用・オフィス用等コーヒーセット」(いずれも複数
銘柄の詰め合わせまたは同一銘柄の3〜4個口バルクセット)は対象外のため
巡回しない。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記2カテゴリ内に「水出しコーヒー」(700〜800cc用の
抽出パック)が1件混在しており非対象。NON_BEAN_KEYWORDSで除外する。
「アイスブレンド」はアイスコーヒー向けに調合された焙煎豆ブレンド
(商品説明で確認済み、パックや瓶入りではない)のため対象に含める。

【重量・価格の取得について】
実データ確認済み: 商品ページにはproduct:price:amount のOGPメタタグが
無く(重量バリエーションにより単一価格が定まらないため)、代わりに
`<option value="ID">100g￥980</option>`のように重量と価格を結合した
テキストが埋め込まれている(半角g/全角ｇの表記ゆれあり)。正規表現で
全ての(重量, 価格)ペアを抽出し、最小重量を代表として採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "さくら珈琲豆店",
    "url": "https://sakura-mame.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "愛知県名古屋市北区金城町2丁目29-3",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://sakura-mame.ocnk.net"
CATEGORY_PATHS = ["product-list/2", "product-list/20"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出しコーヒー"]
WEIGHT_PRICE_PATTERN = re.compile(r"<option value=\"\d+\">(\d+)\s*[gｇ]￥([\d,]+)</option>")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    pids: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select(f'a[href*="{BASE_URL}/product/"]'):
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if m:
                pids.add(m.group(1))
    return [f"{BASE_URL}/product/{pid}" for pid in pids]


def extract_fields(html_text: str) -> dict | None:
    soup = BeautifulSoup(html_text, "html.parser")
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    weight_prices = [(int(w), int(p.replace(",", ""))) for w, p in WEIGHT_PRICE_PATTERN.findall(html_text)]
    if weight_prices:
        weight_g, price = min(weight_prices, key=lambda wp: wp[0])
    else:
        weight_g, price = None, None
    return {"title": title, "price": price, "weight_g": weight_g}


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
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            fields = extract_fields(resp.text)
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
    with open("data_sakuramame.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sakuramame.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
