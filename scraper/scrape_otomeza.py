# -*- coding: utf-8 -*-
"""
scrape_otomeza.py

オトメザ(otomezacoffee.com、東京都江戸川区東葛西、少量多頻度焙煎の
街のロースター)の商品情報を取得する。Jimdo(ジンドゥー、標準の
ショップモジュール)。

robots.txt確認済み(2026-09時点): /app/・/j/はDisallowだが、商品ページ
自体は/app/module/webproduct/goto/がAllow指定で例外的に許可されている。
Crawl-Delay: 5が指定されているためリクエスト間隔を5秒确保する。

【商品名が英語表記である点について】
実データ確認済み: 商品名がすべて英語(産地の国名を含む、例:
"Ethiopia Guji Natural")で記載されており、coffee_parser.pyの
DESIGNATED_BRANDS/国名判定は日本語(カタカナ)表記を前提にしているため
parse_product()では産地を検出できない。そのため商品名の先頭語から
英語国名を直接マッピングするENGLISH_COUNTRY_MAPで判定する
("Mandheling"はスマトラ島の銘柄名のため単独でインドネシアと判定)。

【対象カテゴリについて】
実データ確認済み: sitemap.xmlに/online-store/single-origin/(ストレート
豆、10件)・/online-store/blended-drip-bag-coffee/(ドリップバッグの
ブレンド、対象外)・/online-store/ems-fare/(海外配送料金、対象外)の
3ページがあり、single-originページのみが対象。1ページに全10件が
掲載されておりページネーションは無い。

【商品情報の取得方法について】
実データ確認済み: 一覧ページ自体に商品名(h4.fn[itemprop="name"])・
価格(schema.org Offerのitemprop="price")・重量(バリエーション
セレクトのJSON内weightFormatted、全商品0.2kg=200g)・在庫状況
(itemprop="availability")がすべて構造化データとして埋め込まれており、
詳細ページへの個別アクセスは不要(WOODBERRY COFFEE・豆虎と同じ、
一覧完結パターン)。バリエーションは「豆のまま(coffee beans)」と
「粉(ground coffee)」の2種で価格は同額のため、豆のまま側を採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "オトメザ",
    "url": "https://www.otomezacoffee.com/online-store/single-origin/",
    "platform": "Jimdo",
    "address": "東京都江戸川区東葛西",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/app/・/j/はDisallowだが商品ページは"
                          "/app/module/webproduct/goto/がAllow指定で例外許可。"
                          "Crawl-Delay: 5を遵守)",
}

CATEGORY_URL = "https://www.otomezacoffee.com/online-store/single-origin/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

ENGLISH_COUNTRY_MAP = {
    "ethiopia": "エチオピア",
    "tanzania": "タンザニア",
    "brazil": "ブラジル",
    "guatemala": "グアテマラ",
    "colombia": "コロンビア",
    "mandheling": "インドネシア",
    "kenya": "ケニア",
    "indonesia": "インドネシア",
    "costa rica": "コスタリカ",
    "honduras": "ホンジュラス",
    "panama": "パナマ",
    "rwanda": "ルワンダ",
    "peru": "ペルー",
    "mexico": "メキシコ",
    "yemen": "イエメン",
    "jamaica": "ジャマイカ",
}
WEIGHT_G_PATTERN = re.compile(r"([\d.]+)\s*kg", re.IGNORECASE)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def detect_english_country(title: str) -> str | None:
    lowered = title.lower()
    for en, ja in ENGLISH_COUNTRY_MAP.items():
        if en in lowered:
            return ja
    return None


def pick_bean_variant(select_el) -> dict | None:
    if not select_el:
        return None
    for option in select_el.select("option"):
        label = option.get_text(strip=True)
        if "ground" in label.lower() or "粉" in label:
            continue
        data_raw = option.get("data-params")
        if not data_raw:
            continue
        try:
            return json.loads(data_raw)
        except json.JSONDecodeError:
            continue
    return None


def build_record(card) -> dict | None:
    title_el = card.select_one('h4.fn[itemprop="name"]')
    if not title_el:
        return None
    title = title_el.get_text(strip=True).strip("『』")

    parsed = parse_product(title)
    if not parsed["origin_country"]:
        country = detect_english_country(title)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_title"

    select_el = card.select_one("select.j-product__variants")
    variant = pick_bean_variant(select_el)

    price_el = card.select_one('[itemprop="price"]')
    price = None
    if variant and variant.get("price") is not None:
        price = int(variant["price"])
    elif price_el and price_el.get("content"):
        price = int(float(price_el["content"]))

    weight_g = None
    if variant and variant.get("weightFormatted"):
        m = WEIGHT_G_PATTERN.search(variant["weightFormatted"])
        if m:
            weight_g = int(float(m.group(1)) * 1000)

    availability_el = card.select_one('meta[itemprop="availability"]')
    structural_out_of_stock = bool(availability_el) and "InStock" not in (availability_el.get("content") or "")
    stock_status = detect_stock_status(title, structural_out_of_stock)

    desc_id = card.get("id", "")
    product_url = f"{CATEGORY_URL}#{desc_id}" if desc_id else CATEGORY_URL

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
    soup = fetch_page(CATEGORY_URL)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    for card in soup.select("div.cc-shop-product-desc"):
        detail = build_record(card)
        if detail is None:
            continue

        prev = previous.get(detail["product_url"])
        if is_unchanged(prev, raw_name=detail["raw_name"]):
            records.append(prev)
            continue
        records.append(detail)

    return records, []


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_otomeza.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_otomeza.json に出力しました")
