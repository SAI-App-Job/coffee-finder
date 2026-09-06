# -*- coding: utf-8 -*-
"""
scrape_roastcafe.py

ROAST CAFE(roastcafe.shop-pro.jp、新潟県新潟市江南区曙町3丁目2-7、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【重量違いの重複について】
実データ確認済み: 主力5ブレンドが［200g］／［1kg］の2サイズで個別
商品登録されている。商品名末尾の「［重量］」を除いた基準名で
グルーピングし、最小重量(200g)を代表として採用する。単一産地の商品は
[100g]/[200g]の角括弧表記に加え、商品名中に改行(\\n)が入るケースが
あるため空白に正規化する。

【非コーヒー豆商品の除外について】
実データ確認済み: 全63件のうちオリジナル珈琲ギフト(×2)・ハウス
メイド・ボトルコーヒー(瓶入り液体、RED/WHITE LABELおよびギフト各種)・
カップオンドリップコーヒー(個包装ドリップ形態、各種)・roast cafe latte
base(液体ラテベース、ギフト含む)・ギフト箱・ギフト用メッセージカード
が非対象。NON_BEAN_KEYWORDSで除外する。商品名が空の削除済み
プレースホルダーレコードも除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ROAST CAFE",
    "url": "https://roastcafe.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "新潟県新潟市江南区曙町3丁目2-7",
    "prefecture": "新潟県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://roastcafe.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト", "ボトルコーヒー", "カップ オン ドリップ", "ラテベース"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_BRACKET_PATTERN = re.compile(r"[［\[]\s*\d+\s*(?:kg|[gｇ])\s*[］\]]", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|[gｇ])", re.IGNORECASE)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    return int(m.group(1)) * 1000 if m.group(2).lower() == "kg" else int(m.group(1))


def fetch_raw_items() -> list[dict]:
    items = []
    for product_url in fetch_pid_urls():
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        script_text = ""
        for script in soup.find_all("script"):
            text = script.string or script.get_text() or ""
            if "var Colorme" in text:
                script_text = text
                break
        m = COLORME_PATTERN.search(script_text)
        if not m:
            continue
        data = json.loads(m.group(1))
        product = data.get("product") or {}
        title = re.sub(r"<br\s*/?>", " ", product.get("name") or "")
        title = re.sub(r"[\s　]+", " ", title).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = product.get("sales_price_including_tax") or product.get("sales_price")
        structural_out_of_stock = product.get("stock_num") == 0
        items.append({
            "title": title,
            "price": int(price) if price is not None else None,
            "url": product_url,
            "structural_out_of_stock": structural_out_of_stock,
        })
    return items


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_BRACKET_PATTERN.sub("", item["title"]).strip()
        weight_key = parse_weight_g(item["title"]) or float("inf")
        existing = by_base_name.get(base_name)
        existing_weight = parse_weight_g(existing["title"]) if existing else None
        existing_weight = existing_weight if existing_weight is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


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

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])
    weight_g = parse_weight_g(title)

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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    raw_items = fetch_raw_items()
    canonical_items = pick_canonical_items(raw_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_roastcafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roastcafe.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
