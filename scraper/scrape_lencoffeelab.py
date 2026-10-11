# -*- coding: utf-8 -*-
"""
scrape_lencoffeelab.py

LeN Coffee Lab.(https://shop.len-coffee.jp/、岡山県倉敷市笹沖)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全12商品(すべて100g)を対象とする。ブレンド3種・ストレート9種(デカフェ1種を含む)。商品名がキャッチコピー形式のため、産地は商品説明の「品名」欄から確認して明示した。「芳醇なイルガチェフェ」は浅煎り/中深煎りの選択制のため焙煎度はnull。住所は特商法に番地がなく、フッターの「所在地 〒710-0834 岡山県倉敷市笹沖」(現在ネットショップのみの運営)までとした。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルに重量・販売情報が含まれる、または重量違いの別ページ登録があるため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "LeN Coffee Lab.",
    "url": "https://shop.len-coffee.jp/",
    "platform": "BASE",
    "address": "岡山県倉敷市笹沖",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.len-coffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('73811707', '黄金比のアイスコーヒーブレンド【アイス用ブレンド】', 100, 'ブレンド', None),
    ('114716670', 'スウィートリッチな贅沢コロンビア【中深煎り】', 100, 'ストレート', '中深煎り'),
    ('86222523', '搾りたてのジューシーブレンド【スペシャルブレンド】', 100, 'ブレンド', None),
    ('99908743', '芳醇なイルガチェフェ【浅煎りor中深煎り】', 100, 'ストレート', None),
    ('90089338', '貴方の常識を覆すデカフェ【中深煎り】', 100, 'ストレート', '中深煎り'),
    ('74399659', 'カカオ薫る定番ショコラ【中深煎り】', 100, 'ストレート', '中深煎り'),
    ('74399124', '黒糖のような甘い珈琲コスタリカ【中深煎り】', 100, 'ストレート', '中深煎り'),
    ('101879725', 'カラメルのような甘いコーヒー【中煎り】', 100, 'ストレート', '中煎り'),
    ('73617901', '苦手な人でもブラックで飲める理想の珈琲【中深煎り】', 100, 'ストレート', '中深煎り'),
    ('73720866', '深い余韻に浸る大人ブラックの世界【極深煎り】', 100, 'ストレート', '極深煎り'),
    ('126395928', '完熟のフルーツコーヒー【浅煎り】', 100, 'ストレート', '浅煎り'),
    ('79212827', '蓮ブレンド【レギュラーブレンド】', 100, 'ブレンド', '中深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'114716670': 'コロンビア',
 '99908743': 'エチオピア',
 '90089338': 'グアテマラ',
 '74399659': 'ブラジル',
 '74399124': 'コスタリカ',
 '101879725': 'ニカラグア',
 '73617901': 'グアテマラ',
 '73720866': 'インドネシア',
 '126395928': 'タイ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
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
    with open("data_lencoffeelab.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lencoffeelab.json に出力しました")


if __name__ == "__main__":
    main()
