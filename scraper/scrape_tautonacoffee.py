# -*- coding: utf-8 -*-
"""
scrape_tautonacoffee.py

タウトナコーヒー(shop.tautona-coffee.com、〒870-0841 大分県大分市六坊北町
4-5-2、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【住所について】
特定商取引法ページ(https://shop.tautona-coffee.com/law)で実データ確認済み
(2026-09時点): 事業者の名称「山下周平」、事業者の所在地「〒8700841
大分県大分市六坊北町４−５−２」との記載を確認。候補リストの住所と一致。

【対象商品について】
実データ確認済み(全34件): sitemap.xmlの/items/配下34件のうち、実際に重量
表記(180g)のある焙煎豆単品は6件(ブラジルNO2モジアナ・グアテマラ
クイルコファーマーズ・タンザニアンゴロンゴロ・ディカフェエチオピア・
ニューハウスブレンド・ニューハウスフル)のみ。他はドリップパック(単品/
5パックセット)・水出しコーヒーパック・カフェラテノモト・コーヒー
グラインダー(TIMEMORE)・CAFEC/アバカ/THREE FOR等のペーパーフィルター・
Kalita/bonmac等のドリッパーやドリップポットといった器具のため非対象。
NON_BEAN_KEYWORDSで除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象6件全てで産地スペック(Country/
Fame/Altitude/Variety/Processing System/Aroma・Flavor等)+テイスティング
文(Other/Comment)が入っている。注文/配送案内等の無関係な定型文の混入は
無いため全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "タウトナコーヒー",
    "url": "https://shop.tautona-coffee.com/",
    "platform": "BASE",
    "address": "大分県大分市六坊北町4-5-2",
    "prefecture": "大分県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.tautona-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップパック", "ドリップバッグ", "水出し", "グラインダー", "フィルター",
    "ドリッパー", "メジャーカップ", "ドリップポット", "カフェラテノモト", "CAFEC",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*$")


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
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(title: str, price: int | None, product_url: str, flavor_notes: str | None = None) -> dict | None:
    if not WEIGHT_PATTERN.search(title):
        # 重量表記の無い商品(器具・ドリップパック等)は対象外
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
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        detail = build_record(title, fields["price"], product_url, fields.get("flavor_notes"))
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
    with open("data_tautonacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tautonacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
