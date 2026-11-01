# -*- coding: utf-8 -*-
"""
scrape_kitahirabaisenjo.py

北比良焙煎所(https://kitahirar.base.ec/、滋賀県大津市北比良1043-152)の商品情報を取得する。BASE。

【店舗発見の経緯】
滋賀県・奈良県の新規発掘で発見(2026-11-01)。

【対象商品について】
実データ確認済み(2026-11-01時点): 全15商品(シングル12+ブレンド3)。すべて「生豆時200g」基準の価格で、
焙煎後の実重量は約160g(ABOUT記載)。ここでは表記どおり weight_g=200 を採用する。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では許可)。
本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "北比良焙煎所",
    "url": "https://kitahirar.base.ec/",
    "platform": "BASE",
    "address": "滋賀県大津市北比良1043-152",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE公式ショップ(https://kitahirar.base.ec/)のトップ・ABOUT・各商品ページを2026-11-01に確認。"
                   "住所は特定商取引法に基づく表記。価格は「生豆時200g」基準(焙煎後は約160g)。挽き売りなし。",
    "last_verified_at": "2026-11-01",
}

BASE_URL = "https://kitahirar.base.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5  # BASEは5秒以上

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("149804671", "ブラジル トミオフクダ パレ・ド・クリスタル農園", 200, None, None),
    ("36408609", "コロンビア スプレモ", 200, None, None),
    ("34878439", "グアテマラ SHB Qグレード", 200, None, None),
    ("34878447", "タンザニア AA", 200, None, None),
    ("37908114", "エチオピア イルガチェフェ", 200, None, None),
    ("34878451", "インドネシア トラジャ ランテカルア", 200, None, None),
    ("47550102", "ケニア Qグレード", 200, None, None),
    ("36408855", "カフェインレス コロンビア スプレモ(スイス式水抽出法)", 200, "デカフェ", None),
    ("49983243", "ブラジル セラード 樹上完熟豆 晩秋摘み", 200, None, None),
    ("34878458", "エチオピア ゲイシャ ナチュラル", 200, None, None),
    ("157071662", "ラオス ゲイシャ ウォッシュト", 200, None, None),
    ("38230269", "びわこブレンド", 200, "ブレンド", None),
    ("34878461", "北比良ブレンド", 200, "ブレンド", None),
    ("36895899", "白鬚ブレンド", 200, "ブレンド", None),
    ("162945726", "ナイトブレンド", 200, "ブレンド", None),
]

ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc_full = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
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
        "flavor_notes": desc_full[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products():
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
    with open("data_kitahirabaisenjo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kitahirabaisenjo.json に出力しました")


if __name__ == "__main__":
    main()
