# -*- coding: utf-8 -*-
"""
scrape_kappacoffee.py

かっぱ印の珈琲豆店(kappacoffee.base.shop、鳥取県境港市上道町3600、自家焙煎豆の
オンライン販売)の商品情報を取得する。BASE(同一店舗がkappa-to-coffee.stores.jp
というSTORESのショップも運営しているが、候補リストの指示どおりBASE側を採用)。

【住所について】
公式ストアの特定商取引法ページ(https://kappacoffee.base.shop/law)で実データ
確認済み(2026-09時点): 「事業者の名称 岡部道孝 / 事業者の所在地　〒6840033
鳥取県境港市上道町3600」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【「店舗受取」表記について】
実データ確認済み(2026-09時点、全20件): 全商品名が「【店舗受取】」で始まる。
BASEの決済機能を使いつつ受け取りは店舗のみという運用だが、産地・価格情報は
通常のBASE商品ページと同様に構造化されているため通常のBASEショップと同じ
方法でスクレイピング可能。「【店舗受取】」接頭辞は産地判定の妨げになるため
除去する。

【重量違いの重複について】
実データ確認済み: 全10銘柄がそれぞれ150g/300gの2サイズで別商品として登録
されている(バリアントではない)。商品名末尾の「・焙煎豆150g」「・焙煎豆300g」
を除いた基準名でグルーピングし、最小重量(150g)を代表として採用する。

【非コーヒー豆商品について】
実データ確認済み: 全20件がいずれも産地名を持つ焙煎豆単品で、非コーヒー豆商品は
無かった。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象10件全てでテイスティング文・産地
背景・香り/甘味/苦味/酸味/コクの★評価が入っており(生産地域/標高/品種等の
スペック情報が地続きで混在するがfull-text-tolerance方針により許容)、
注文/配送案内等の無関係な定型文の混入は無いため全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "かっぱ印の珈琲豆店",
    "url": "https://kappacoffee.base.shop/",
    "platform": "BASE",
    "address": "鳥取県境港市上道町3600",
    "prefecture": "鳥取県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://kappacoffee.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PICKUP_PREFIX_PATTERN = re.compile(r"^【店舗受取】\s*")
WEIGHT_SUFFIX_PATTERN = re.compile(r"[・･]焙煎豆\s*(\d+)\s*[gｇ]\s*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def fetch_item_fields(url: str) -> dict | None:
    soup = fetch_page(url)
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].split(" powered by BASE")[0].strip()
    title = PICKUP_PREFIX_PATTERN.sub("", title)
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "url": url, "flavor_notes": flavor_notes or None}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for item in items:
        weight_m = WEIGHT_SUFFIX_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        base = WEIGHT_SUFFIX_PATTERN.sub("", item["title"]).strip()
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if not title:
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

    weight_m = WEIGHT_SUFFIX_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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

    items = []
    for item_url in item_urls:
        try:
            fields = fetch_item_fields(item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
        if fields:
            items.append(fields)

    canonical_items = pick_canonical_items(items)

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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kappacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kappacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
