# -*- coding: utf-8 -*-
"""
scrape_taxcocoffee.py

タスコ珈琲(https://taxcocoffee.base.shop/、愛知県江南市古知野町小金113番地3)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛知県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全32商品のうち、カテゴリ「ブレンドコーヒー」6点と「ストレートコーヒー」8点の200g入り焙煎豆14点。生豆・ドリップバッグ・水出しバッグ・リキッド・ギフトセットは除外。公式の旧CGIカート(konan-beans.com/cart/cart.cgi)は採用せずBASEを採用。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "タスコ珈琲",
    "url": "https://taxcocoffee.base.shop/",
    "platform": "BASE",
    "address": "愛知県江南市古知野町小金113番地3",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "公式 https://konan-beans.com/shop.html(「創業以来、直火焙煎にこだわり」、江南市古知野町小金113番地3、カフェ併設)、BASE https://taxcocoffee.base.shop/ のカテゴリ「ブレンドコーヒー」「ストレートコーヒー」を2026-10-20に確認",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://taxcocoffee.base.shop"
REQUEST_INTERVAL = 5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('78973520', 'マイルドブレンド', 200, 'ブレンド', 'ハイロースト'),
    ('112801952', 'こちのブレンド', 200, 'ブレンド', 'ハイロースト'),
    ('78974154', 'ジャーマンブレンド', 200, 'ブレンド', 'シティロースト'),
    ('131348358', 'シティブレンド', 200, 'ブレンド', 'シティロースト'),
    ('78973767', 'ゴリラブレンド', 200, 'ブレンド', 'フレンチロースト'),
    ('112802588', 'アイスブレンド', 200, 'ブレンド', 'ハイロースト'),
    ('155679201', '秋の珈琲(期間限定10月31日まで)', 200, 'ブレンド', 'ハイロースト'),
    ('134535443', 'フレンチロースト タンザニアKIBO・AA', 200, None, 'フレンチロースト'),
    ('134535260', 'マンデリン トバコ', 200, None, 'フルシティロースト'),
    ('102719382', 'モカフレンチ・シダモ', 200, None, 'フレンチロースト'),
    ('102719297', 'キリマンジャロ・KIBO・AA', 200, None, 'ハイロースト'),
    ('102530625', 'ホンジュラスHG', 200, None, 'ミディアムロースト'),
    ('102522496', 'ドミニカAAバラオナ', 200, None, 'ミディアムロースト'),
    ('102521671', 'コロンビア・ラ・バージニア', 200, None, 'ハイロースト'),
    ('102145732', 'ガテマラ・ステイゴールド', 200, None, 'ハイロースト'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'134535443': 'タンザニア', '102719382': 'エチオピア', '102719297': 'タンザニア', '102145732': 'グアテマラ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    time.sleep(REQUEST_INTERVAL)  # BASEは5秒以上の間隔
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
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
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

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
        "roast_hint": None,
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
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_taxcocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_taxcocoffee.json に出力しました")


if __name__ == "__main__":
    main()
