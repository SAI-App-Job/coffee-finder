# -*- coding: utf-8 -*-
"""
scrape_coffeemaki.py

珈琲maki(Coffee Maki、coffeemaki.base.shop、〒814-0104
福岡県福岡市城南区別府5-22-1、自家焙煎豆専門店)の商品情報を取得する。
BASE(白ラベルドメイン)。

【住所について】
特定商取引法ページ(https://coffeemaki.base.shop/law)で「〒814-0104
福岡県福岡市城南区別府５丁目２２−１」を確認済み(2026-09時点)。BASE社の
代理住所(東京都渋谷区/港区等)ではなく、店舗自身の福岡市城南区の住所
であることを確認した上で採用する。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全27件): ドリップバッグ各種・「珈琲豆定期便」
「ドリップバッグ定期便」(サブスクリプション)・「水出し珈琲」
「デカフェ水出し珈琲」(ボトル飲料形態)・「ギフトボックス」各種が
非対象。NON_BEAN_KEYWORDSで除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionは対象9件全てでテイスティング文+生産
工程/品種/標高/焙煎度等のスペック情報が地続きで混在しており(ラベル
区切りなし)、full-text-tolerance方針により全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲maki",
    "url": "https://coffeemaki.base.shop/",
    "platform": "BASE",
    "address": "福岡県福岡市城南区別府5-22-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeemaki.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "定期便", "水出し珈琲", "ギフトボックス"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
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


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
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
    product_urls = fetch_sitemap_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue

        detail = build_record({
            "title": fields["title"],
            "price": fields["price"],
            "flavor_notes": fields.get("flavor_notes"),
            "url": product_url,
        })
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
    with open("data_coffeemaki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeemaki.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
