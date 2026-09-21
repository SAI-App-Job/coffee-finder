# -*- coding: utf-8 -*-
"""
scrape_inadacoffee.py

いなだ珈琲舎(inadacoffee.thebase.in、岩手県盛岡市南大通1丁目12-18 松栄館
1F、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
BASEストアのトップページ本文中に「岩手県盛岡市南大通1丁目12-18　松栄館
１階」との記載を実データ確認済み(2026-09時点)。候補リストの住所と一致。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【対象商品について】
実データ確認済み(sitemap.xml全20件): ストレート9種・ブレンド2種・デカフェ
1種(いずれも200g、重量違いの重複なし)が対象。デカフェ(【デカフェ】
コロンビア)は産地が明示されているため対象に含める。ギフトボックス(2件)・
ドリップバッグ/ドリップパック単品及び詰め合わせ(5件)・マスターおすすめ
セット(複数銘柄の70g×3種詰め合わせ)は非対象のためNON_BEAN_KEYWORDSで
除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionにテイスティング文が直接入っており
(対象12件全て確認)、大半の商品には末尾に「※(1回|１回|一回)のご注文で、
すべての商品の合計が1200g以上お求めのお客様は、電話(または|か)FAXにて
ご注文ください。」という店舗共通の注意書きが続く(「または」表記に
「またはAXにて」という店舗側のタイプミスも確認済み)。その手前までを
採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "いなだ珈琲舎",
    "url": "https://inadacoffee.thebase.in/",
    "platform": "BASE",
    "address": "岩手県盛岡市南大通1丁目12-18 松栄館1F",
    "prefecture": "岩手県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://inadacoffee.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト", "ドリップバッグ", "ドリップパック", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"※.?回のご注文で")


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    m = FLAVOR_STOP_PATTERN.search(description)
    text = description[: m.start()] if m else description
    return text.strip() or None


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
    flavor_notes = extract_flavor_notes(desc_el["content"]) if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


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
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({
            "title": title,
            "price": fields["price"],
            "url": product_url,
            "flavor_notes": fields.get("flavor_notes"),
        })

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
    with open("data_inadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_inadacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
