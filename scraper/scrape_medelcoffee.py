# -*- coding: utf-8 -*-
"""
scrape_medelcoffee.py

medel coffee(メデルコーヒー、medelcoffee.thebase.in、鳥取県鳥取市千代水2-77、
自家焙煎スペシャルティコーヒーのオンライン販売)の商品情報を取得する。BASE。

【住所について】
公式ストアの特定商取引法ページ(https://medelcoffee.thebase.in/law)で実データ
確認済み(2026-09時点): 「事業者の名称 松本豪 / 事業者の所在地　〒6800911
鳥取県鳥取市千代水2-77」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【商品構成について】
実データ確認済み(2026-09時点、全5件): 産地名を国名の英語表記で角括弧付き
「-BRAZIL-」のように商品名末尾に付けた単一銘柄が4件(いずれも重量表記は無いが
実データで全品150gの単一サイズと確認)、「ドリップバッグ　2種」1件が非対象。
NON_BEAN_KEYWORDSで除外する。

【原産国について】
実データ確認済み: 商品名が「Luzia -BRAZIL-」のように農園名+英語国名の構成で、
coffee_parser.ORIGIN_COUNTRY_KEYWORDS_ENが英語国名を検出する。

【flavor_notes(2026-09-22追記)】
実データ確認済み: og:descriptionに対象4件全てで極めて詳細なテイスティング
文・農園情報・抽出レシピ等が入っている。1件(KARUMANDI-KENYA)のみ末尾に
「※クリックポストで送れる豆量は300gまでです。...」という配送方法の
定型文が続くため、この直前で打ち切る(他3件には該当箇所なし)。それ以外の
無関係な定型文の混入は無いため全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "medel coffee",
    "url": "https://medelcoffee.thebase.in/",
    "platform": "BASE",
    "address": "鳥取県鳥取市千代水2-77",
    "prefecture": "鳥取県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://medelcoffee.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ドリップバック"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 150  # 理由はモジュールdocstring参照
FLAVOR_STOP_PATTERN = re.compile(r"※クリックポストで送れる")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].split(" powered by BASE")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    flavor_notes = flavor_notes or None

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
    weight_g = int(weight_m.group(1)) if weight_m else FIXED_WEIGHT_G

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
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for item_url in item_urls:
        try:
            detail = build_record(fetch_page(item_url), item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
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
    with open("data_medelcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_medelcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
