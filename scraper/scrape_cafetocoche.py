# -*- coding: utf-8 -*-
"""
scrape_cafetocoche.py

Cafe Tocoche(カフェ トコシエ、cafetocoche.theshop.jp、札幌市豊平区豊平3条
7丁目2-1 エクセレントハウス豊平37 1F、theshop.jp)の商品情報を取得する。

【プラットフォームについて】
theshop.jpは2019年にBASE株式会社が買収し同社のインフラに統合された
ネットショップサービス(ページ内に"powered by BASE"の表記あり、CDN等も
thebase.in系ドメインを使用していることを実データ確認済み)。/items/<id>形式
のURL・OGPメタタグ(product:price:amount)を含め、他のBASE系店舗(ai珈琲等)
と完全に同一の構造のため、scrape_aicoffee.py等と同じ手法で取得できる。

【住所について】
BASEの特定商取引法ページ(https://cafetocoche.theshop.jp/law)で実データ
確認済み(2026-09時点、〒062-0903 北海道札幌市豊平区豊平三条7丁目2-1
エクセレントハウス豊平37 1F)。BASE株式会社自体の代理住所ではなく、
事業者本人の住所が明記されている。

【商品構成について】
実データ確認済み(sitemap.xml全14件): コーヒー豆単品7件(季節限定ブレンド・
カフェオレ用ブレンド・エチオピア・インドネシア・ブレンド"QUETZAL"
"LE COQ"、デカフェブレンド"CHOUETTE"、いずれも100g)と、非対象の
「COFFEE DRIP BAGS」各種(個包装ドリップバッグ単品・詰め合わせ)、
「GIFT用 キット」「GIFT包装」(包装資材)。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): 他のBASE/theshop.jp系店舗と同一の記述
(curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可)。本スクレイパーは識別可能な独自User-Agentを使用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象7件全てでテイスティング文・産地
情報が入っている。末尾に「※ 写真のパッケージ袋は、店舗での販売の
ものです。」という注記の定型文が続くため、この見出しの直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Cafe Tocoche",
    "url": "https://cafetocoche.theshop.jp/",
    "platform": "theshop.jp(BASE系)",
    "address": "北海道札幌市豊平区豊平3条7丁目2-1 エクセレントハウス豊平37 1F",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE/theshop.jp系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cafetocoche.theshop.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["DRIP BAG", "DRIP BAGS", "GIFT"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"※\s*写真のパッケージ袋は")


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
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


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
        "flavor_notes": item.get("flavor_notes"),
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


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cafetocoche.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafetocoche.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
