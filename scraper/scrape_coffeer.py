# -*- coding: utf-8 -*-
"""
scrape_coffeer.py

Coffeer(coffeer.base.shop、鹿児島県鹿児島市名山町3-7)の商品情報を取得する。BASE。
BASEのrobots.txtは python-requests/curl 等を個別にDisallowしているため、識別可能な独自User-Agentを使い、
リクエスト間隔は5秒以上空ける。

【対象商品】豆は9銘柄(ブレンド3種[季節の趣味ブレンド(秋)・スタンダード・ノアール]+シングル5種+デカフェ・ブラジル)を
250g/500gの2容量で掲載。100g単位の商品はないため最小の250gを代表にする(豆のまま/粉の選択あり、同価格)。
ドリップバッグ5個セットは除外。焙煎度の個別表記はないため null(店は深煎り専門を掲げる)。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "Coffeer",
    "url": "https://coffeer.base.shop/",
    "platform": "BASE",
    "address": "鹿児島県鹿児島市名山町3-7",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-11確認。python-requests/curl等は個別にDisallow、User-agent: * は/cart/等以外許可。識別可能なUser-Agentを使用)",
    "source_note": "公式 https://coffeer.base.shop/ ・/about ・特商法 /law を2026-11-02に確認。ブログ最新は2026-09-01(秋の趣味ブレンド)。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://coffeer.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5.5

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")

# (商品ID, 商品名, 重量(g), 分類, 産地の上書き)
ITEMS = [
    ("121269772", "【秋】趣味ブレンド", 250, "ブレンド", None),
    ("103806575", "スタンダードブレンド", 250, "ブレンド", None),
    ("103807378", "ノアールブレンド", 250, "ブレンド", None),
    ("103807587", "イルガチェフ・モカ", 250, "ストレート", "エチオピア"),
    ("103807783", "ブラジル", 250, "ストレート", None),
    ("103807894", "デカフェ・ブラジル", 250, "デカフェ", "ブラジル"),
    ("103808000", "ルワンダ", 250, "ストレート", None),
    ("103808140", "マンデリン", 250, "ストレート", None),
    ("103808265", "グァテマラ", 250, "ストレート", None),
]


def build_record(item_id: str, name: str, weight_g: int, category: str, origin_override: str | None) -> dict:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = resp.text
    desc_m = DESC_PATTERN.search(text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:300] if desc_m else None
    price_m = PRICE_PATTERN.search(text)
    pur_m = PURCHASABILITY_PATTERN.search(text)
    sold_out = bool(pur_m) and pur_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if category == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    elif origin_override:
        parsed["origin_country"] = origin_override
        parsed["origin_source"] = "raw_name"
    elif not parsed["origin_country"]:
        parsed["origin_country"] = detect_country_name(name)
        parsed["origin_source"] = "raw_name" if parsed["origin_country"] else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": None,
        "flavor_notes": desc,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, cat, ov in ITEMS:
        try:
            records.append(build_record(item_id, name, weight_g, cat, ov))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    with open("data_coffeer.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeer.json に出力しました")


if __name__ == "__main__":
    main()
