# -*- coding: utf-8 -*-
"""
scrape_brocantecoffee.py

brocante coffee(https://brocante.base.shop/、兵庫県西宮市神楽町11-20)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(兵庫県)の新規発掘で発見。住所は特商法ページ(https://brocante.base.shop/law)と食べログ(https://tabelog.com/hyogo/A2803/A280301/28047323/)の記載、実店舗・自家焙煎はRetty・にしつーグルメ等の紹介記事で確認(2026-10-26)。

【対象商品について】
実データ確認済み(2026-10時点): 商品23件のうち、単品の焙煎豆3銘柄(ブレンド RICO・マンデリン G1・エチオピア グジ、いずれも200g)が対象。
ドリップバッグ各種、お豆3種セット(100g×3)、10種セット(20g×10)、水出しパック、ギフトは除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description

SHOP_INFO = {
    "name": "brocante coffee",
    "url": "https://brocante.base.shop/",
    "platform": "BASE",
    "address": "兵庫県西宮市神楽町11-20",
    "prefecture": "兵庫県",
    "source_note": "https://brocante.base.shop/ の商品ページ・/lawを2026-10-20時点で確認。住所は特商法と食べログ(西宮市神楽町11-20)で一致。店頭・ドリップバッグ等も販売する自家焙煎珈琲店",
    "last_verified_at": "2026-10-20",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://brocante.base.shop"
REQUEST_INTERVAL_SEC = 5  # BASEは5秒以上
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("80387260", "ブレンド RICO", 200, "ブレンド", "中深煎り"),
    ("109273100", "エチオピア シダモ グジ モルドコフ農園", 200, None, "中浅煎り"),
    ("121824632", "インドネシア マンデリン G1 アチェ アットソース+", 200, None, "中深煎り"),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {"109273100": "エチオピア", "121824632": "インドネシア"}

DESC_SPLIT_PATTERN = re.compile(r"[◇□▪︎]|\s{2,}")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1)).split("□内容量")[0]).strip()[:400] if desc_m else None
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
        if not parsed["processing_method"] and desc:
            parsed["processing_method"] = extract_from_description(DESC_SPLIT_PATTERN.sub("\n", desc))["processing_method"]
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
    for i, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
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
    with open("data_brocantecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_brocantecoffee.json に出力しました")


if __name__ == "__main__":
    main()
