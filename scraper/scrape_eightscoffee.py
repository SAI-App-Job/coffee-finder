# -*- coding: utf-8 -*-
"""
scrape_eightscoffee.py

EIGHTS COFFEE(https://8scoffee.official.ec/、山梨県北杜市大泉町西井出8240-8037)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(山梨県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASEの商品全16点のうち、珈琲豆200g(ブレンド3種+シングル11種)の14点を対象とする。ドリップスタイルとキャニスター(防湿缶)は除外。公式サイト8scoffee.com、特商法ともに住所は北杜市大泉町西井出8240-8037。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが重量・キャッチコピー付きの表記のため)。
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
    "name": "EIGHTS COFFEE",
    "url": "https://8scoffee.official.ec/",
    "platform": "BASE",
    "address": "山梨県北杜市大泉町西井出8240-8037",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://8scoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('82907513', 'EIGHTS BLEND', 200, 'ブレンド', '中深煎り'),
    ('82908052', 'HOKUTO BLEND', 200, 'ブレンド', '深煎り'),
    ('82908075', 'ICE BLEND', 200, 'ブレンド', '深煎り'),
    ('82908381', 'ブラジル プラナウト農園 ナチュラル', 200, None, '深煎り'),
    ('82908317', 'コロンビア マグダレナ SUP ウォッシュド', 200, None, '深煎り'),
    ('82908579', 'コロンビア シルキーゴールド カフェインレス 液体CO2処理', 200, None, '中深煎り'),
    ('82908562', 'コスタリカ ガンボア農園 ブラックハニー', 200, None, '浅煎り'),
    ('82908122', 'コスタリカ ガンボア農園 ウォッシュド', 200, None, '中深煎り'),
    ('82908498', 'エチオピア イルガチャフィー G1 ナチュラル', 200, None, '浅煎り'),
    ('82908531', 'エチオピア イルガチャフィー G1 ウォッシュド', 200, None, '浅煎り'),
    ('82908430', 'グアテマラ アゾテア農園 ウォッシュド', 200, None, '中深煎り'),
    ('82908456', 'グアテマラ オリエンテ ナチュラル', 200, None, '中深煎り'),
    ('82908483', 'インドネシア マンデリン ビンタンリマ', 200, None, '深煎り'),
    ('82907265', 'ケニア マサイ AA ウォッシュド', 200, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

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
    with open("data_eightscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_eightscoffee.json に出力しました")


if __name__ == "__main__":
    main()
