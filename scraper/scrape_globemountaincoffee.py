# -*- coding: utf-8 -*-
"""
scrape_globemountaincoffee.py

グローブマウンテン珈琲(https://shop.globe-mountain-coffee.com/、京都府京都市中京区西ノ京東中合町55 ハイツウエストロード1階)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-21): 全14商品のうち、豆6銘柄(ブレンド4・シングル2)を収録。
アイスコーヒー(液体)・ドリップバッグ・砂糖・グラノーラ・フィルターは除外。
ブレンド4種は内容量の選択(100g/200g/600g)があり、最小の100g(ベース価格)を採用。シングル2種は商品名が100gの単品。
豆のまま/ペーパーフィルター・コーヒーメーカー用(粉)の選択式で、価格は同一(豆のままを採用)。
実店舗: 京都市中京区の「グローブマウンテン珈琲」(/aboutに店舗情報・営業時間)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可、/cart/ 等のみ禁止)。本スクレイパーは識別可能な独自User-Agentを使用し、
リクエスト間隔は5秒以上とする。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {'name': 'グローブマウンテン珈琲',
 'url': 'https://shop.globe-mountain-coffee.com/',
 'platform': 'BASE',
 'address': '京都府京都市中京区西ノ京東中合町55 ハイツウエストロード1階',
 'prefecture': '京都府',
 'robots_txt_status': '実質許可(2026-10-21確認。User-agent: '
                      '*は許可で/cart/等のみ禁止、python-requests/curlは個別にDisallow。識別可能なUser-Agentを使用)',
 'source_note': 'BASE独自ドメイン(https://shop.globe-mountain-coffee.com/)のトップ(全14商品)・各商品ページ・/about・/law(特商法)を2026-10-21に確認。公式サイト(globe-mountain-coffee.com)はshop側へ転送。/aboutに「コーヒー豆はすべて京都にある実店舗…の富士ローヤル5kgで丁寧に焙煎」。新着日付の表記なし',
 'last_verified_at': '2026-10-21'}

BASE_URL = "https://shop.globe-mountain-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 焙煎度の補足(roast_hint))
ITEMS = [
    ('4956735', 'オリジナルブレンド 中深煎り', 100, 'ブレンド', '中深煎り', None),
    ('4956763', 'ユーロビターブレンド 深煎り', 100, 'ブレンド', '深煎り', None),
    ('4956752', 'ミスティブレンド 中煎り', 100, 'ブレンド', '中煎り', None),
    ('13628702', 'ワーカーズブレンド 極深煎り', 100, 'ブレンド', '極深煎り', None),
    ('120514529', 'エチオピア グジ ディムトゥ G1 ナチュラル 中煎り', 100, None, '中煎り', None),
    ('101206095', '東ティモール マウベシ 深煎り', 100, None, '深煎り', None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None, roast_hint: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    full_desc = html_lib.unescape(desc_m.group(1)) if desc_m else None
    desc = re.sub(r"\s+", " ", full_desc).strip()[:400] if full_desc else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"
    if not parsed["processing_method"] and full_desc:
        parsed["processing_method"] = extract_from_description(full_desc.replace("生産処理：", "精選方法："))["processing_method"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
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
    for item_id, name, weight_g, category_override, roast_level, roast_hint in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, roast_hint)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_globemountaincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_globemountaincoffee.json に出力しました")


if __name__ == "__main__":
    main()
