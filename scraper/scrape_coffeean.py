# -*- coding: utf-8 -*-
"""
scrape_coffeean.py

可否庵(https://coffeean.thebase.in/、徳島県徳島市幸町2-30)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(徳島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全32商品(100g/200gのペア16銘柄)のうち、同一銘柄が100g/200gで別ページ登録されているため100gを代表として収録した16商品(シングル10・ブレンド5・ドミニカ等)。公式サイトは coffeean1980.com、住所は特定商取引法表記(徳島県徳島市幸町2丁目30)で確認。焙煎度は商品説明の「焙煎度」表記による。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが重量違いの重複登録・キャッチコピー付きのため)。
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
    "name": "可否庵",
    "url": "https://coffeean.thebase.in/",
    "platform": "BASE",
    "address": "徳島県徳島市幸町2-30",
    "prefecture": "徳島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeean.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('5374669', 'グアテマラ エル インヘルト', 100, None, '浅煎り'),
    ('104988256', 'ブラジル ショコラ ピーベリー', 100, None, '深煎り'),
    ('104987030', 'コロンビア エルパライソ ライチ', 100, None, '浅煎り'),
    ('104982445', 'ニカラグア サンホセ イエローパカマラ', 100, None, '浅煎り'),
    ('5374655', '可否庵ブレンド', 100, 'ブレンド', '中深煎り'),
    ('5374657', 'ストロングブレンド', 100, 'ブレンド', '深煎り'),
    ('31106505', 'ケニア', 100, None, '浅煎り'),
    ('6726148', 'アイスコーヒーブレンド', 100, 'ブレンド', '深煎り'),
    ('35594845', 'めぐる、オリジナルブレンド', 100, 'ブレンド', '深煎り'),
    ('8477337', 'ドミニカ', 100, None, '深煎り'),
    ('8782796', 'ブラジル ショコラ', 100, None, '中深煎り'),
    ('5374659', 'モカ', 100, None, '浅煎り'),
    ('5374665', 'ブラジル', 100, None, '中深煎り'),
    ('5374671', 'ベトナム', 100, None, '中深煎り'),
    ('5374675', 'セレベス', 100, None, '中深煎り'),
    ('5374677', 'マンデリン', 100, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'5374659': 'エチオピア', '8477337': 'ドミニカ共和国', '5374675': 'インドネシア', '5374677': 'インドネシア', '5374671': 'ベトナム'}

DESC_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    if item_id in DESC_OVERRIDES:
        desc = DESC_OVERRIDES[item_id]
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
    with open("data_coffeean.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeean.json に出力しました")


if __name__ == "__main__":
    main()
