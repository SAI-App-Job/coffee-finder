# -*- coding: utf-8 -*-
"""
scrape_jincoffeekatsunuma.py

JIN COFFEE Katsunuma(https://jincoffee.base.shop/、山梨県甲州市勝沼)の商品情報を取得する。BASE。
住所は番地まで確認できていない(市区町村までの記載)。

【店舗発見の経緯】
全国再調査(山梨県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-12時点): 全35商品のうち、自家焙煎豆(90g)13銘柄を対象とする。
除外: ギフト(SUN/MOON Stories等6件)、世界観の説明ページ2件(購入不可・価格9,999,999円)、
勝沼ワインリッチコーヒー(ドリップバッグ・セット11件)、定期便3件。
内容量は商品名の「90g」表記(100g未満)。ブルーマウンテンは50gと90gが別商品で並ぶため、
店の標準規格である90gを代表とした(50gは1,800円)。ハワイコナ2種は品切れ(unpurchasable)。
焙煎度は商品説明に記載があるものだけ転記し、記載なしはNone。

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
    "name": "JIN COFFEE Katsunuma",
    "url": "https://jincoffee.base.shop/",
    "platform": "BASE",
    "address": "山梨県甲州市勝沼",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://jincoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('118074937', '【秋季限定】十三夜ブレンド 〜夜空に浮かぶ微笑み〜', 90, 'ブレンド', '中深煎り'),
    ('83506151', 'JIN-BLEND original', 90, 'ブレンド', '中煎り'),
    ('122490659', 'JinBlend Rouge(ルージュ)', 90, 'ブレンド', '中深煎り'),
    ('104865558', 'Jin-Blend Noir(ノアール) 〜黒の誘惑〜', 90, 'ブレンド', None),
    ('104647244', '初恋ブレンド 〜懐かしい思い出〜', 90, 'ブレンド', '中煎り'),
    ('95466813', 'ハワイコナ No.1', 90, None, 'ミディアムロースト'),
    ('95226430', 'ハワイコナ エクストラファンシー', 90, None, None),
    ('81626881', 'コロンビア スプレモ', 90, None, None),
    ('81629338', 'タンザニア キリマンジャロAA(イエンガ村ロット)', 90, None, None),
    ('78977254', 'ブラジル ショコラ サンアントニオ', 90, None, None),
    ('75157116', 'グアテマラ SHB ウエウエティナンゴ', 90, None, None),
    ('77699741', 'エチオピア(イルガチェフェ)G1 チェルベサ ナチュラル', 90, None, '中煎り'),
    ('87178520', 'ブルーマウンテン No1', 90, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'87178520': 'ジャマイカ', '95466813': 'アメリカ(ハワイ)', '95226430': 'アメリカ(ハワイ)'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
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
    with open("data_jincoffeekatsunuma.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jincoffeekatsunuma.json に出力しました")


if __name__ == "__main__":
    main()
