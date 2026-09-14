# -*- coding: utf-8 -*-
"""
scrape_dollscoffee.py

どるず珈琲店(ec.dolls-coffee.jp、秋田県秋田市中通4-7-35 秋田市民市場内、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(白ラベルドメイン)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
特定商取引法ページ(https://ec.dolls-coffee.jp/law)で実データ確認済み
(2026-09時点): 「秋田市中通4-7-35秋田市民市場内(サンクス側入口)」との
記載を確認。候補リストの住所と一致。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【重量について】
実データ確認済み: 商品名自体に重量表記が無く、100g/200gはセレクトボックス
の option要素(例:「100g」「200g ＋ ¥860」)から選ぶ形式。追加料金の無い
100gが基準価格(og:price)に対応するため、最小重量(セレクト内の追加料金無し
の選択肢)を採用する(ai珈琲と同じ方式)。

【対象商品について】
実データ確認済み(sitemap.xml全23件): スペシャルティコーヒー豆(ブレンド2種
+ストレート5種、計7件)が対象。ドリップバッグ・カフェオレベース(無糖/加糖・
各種本数セット)・スペシャルティアイスコーヒー(瓶入り・セット)・
「ニコジーコーヒー」(定期コース・お試し1回分・ドリップバッグセットの
サブスクリプション型商品)は非対象のためNON_BEAN_KEYWORDSで除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "どるず珈琲店",
    "url": "https://ec.dolls-coffee.jp/",
    "platform": "BASE",
    "address": "秋田県秋田市中通4-7-35 秋田市民市場内",
    "prefecture": "秋田県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://ec.dolls-coffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "カフェオレベース", "アイスコーヒー", "ニコジー"]
WEIGHT_OPTION_PATTERN = re.compile(r">\s*(\d+)\s*[gｇ]\s*(?:</option>|\s)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_fields(soup: BeautifulSoup, html: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    weight_matches = [int(m.group(1)) for m in WEIGHT_OPTION_PATTERN.finditer(html)]
    weight_g = min(weight_matches) if weight_matches else None

    return {"title": title, "price": price, "weight_g": weight_g}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


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
        fields = extract_fields(soup, resp.text)
        if not fields:
            continue
        if any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
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


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_dollscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dollscoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
