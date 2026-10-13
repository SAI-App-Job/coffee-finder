# -*- coding: utf-8 -*-
"""
scrape_nonakacoffee.py

焙煎珈房NONAKA(https://nonakacoffee.thebase.in/、愛媛県松山市東野2丁目6-10)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛媛県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): サイトマップ73商品のうち、100g出品の豆25銘柄(ブレンド7・シングル17・デカフェ1)を収録(各銘柄は100gと300gが別商品。最小重量の100gを代表に採用、300gは除外)。除外: アイスコーヒーリキッド・カフェ・オ・レベース・ドリップバッグ・珈琲豆詰合せ・アイスコーヒー詰合せ等のセット/液体/ドリップバッグ。「nonakaﾌﾞﾚﾝﾄﾞ」「ロイヤルブラック」(商品説明からブレンド)は分類をブレンドに指定。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが容量表記・キャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎珈房NONAKA",
    "url": "https://nonakacoffee.thebase.in/",
    "platform": "BASE",
    "address": "愛媛県松山市東野2丁目6-10",
    "prefecture": "愛媛県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://nonakacoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('1461060', 'nonakaﾌﾞﾚﾝﾄﾞ', 100, 'ブレンド', None),
    ('1461166', 'クリスタルブレンド', 100, None, None),
    ('1461172', 'ロイヤルビターブレンド', 100, None, None),
    ('1461180', 'クラシックブレンド', 100, None, None),
    ('1461182', 'ソフトブレンド', 100, None, None),
    ('1487652', 'ロイヤルブラック', 100, 'ブレンド', None),
    ('1609178', 'ペルー・チャンチャマイヨ', 100, None, None),
    ('1487772', 'メキシコ・アルツラ', 100, None, None),
    ('1609190', 'グァテマラ・アンティグア', 100, None, None),
    ('1609228', 'コスタリカ', 100, None, None),
    ('1487787', 'エルサルバドル', 100, None, None),
    ('1609299', 'ブラジル・プリマヴェーラ', 100, None, None),
    ('1657020', 'コロンビア・クレオパトラ', 100, None, None),
    ('1609321', 'ドミニカ・カリビアンクィーン', 100, None, None),
    ('1609329', 'キューバ・クリスタルマウンテン', 100, None, None),
    ('1609349', 'タンザニア・キボー', 100, None, None),
    ('1656991', 'エチオピア・モカ・シダモ', 100, None, None),
    ('1609204', 'マンデリン・スマトラタイガー', 100, None, None),
    ('1655399', 'イエメン・モカ・マタリ', 100, None, None),
    ('12148531', 'ホンジュラス', 100, None, None),
    ('10850702', 'エチオピア・グジ\u3000ナチュラル', 100, None, None),
    ('4023148', '秋スペシャルブレンド', 100, None, None),
    ('1656995', 'トラジャ', 100, None, None),
    ('1657026', 'ケニアABクィーンアリーヤ', 100, None, None),
    ('114883649', 'カフェインレスコーヒー', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'1656995': 'インドネシア'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
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
        "roast_level": roast_level,  # 商品名の「ハイブリッド」等がハイロースト誤検出されるため、明示値のみ採用
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
    with open("data_nonakacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nonakacoffee.json に出力しました")


if __name__ == "__main__":
    main()
