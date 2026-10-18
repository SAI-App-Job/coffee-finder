# -*- coding: utf-8 -*-
"""
scrape_koigauracoffee.py

恋ヶ浦コーヒーロースト(https://koigaura-coffeeroast.com/、宮崎県串間市大納2608-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(宮崎県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): ストア(koigaura.base.shop)の全29商品のうち豆14銘柄(1袋は生豆240gを焙煎し焼き上がり約200g)。水出しパック・ドリップパック・ドリップギフト・ステッカー・コラボ品は除外。住所はBASEの特商法がBASE社の住所のため、確認済みの〒888-0221 宮崎県串間市大納2608-1を採用。ご注文後の発送日当日に焙煎する形式。
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
    "name": "恋ヶ浦コーヒーロースト",
    "url": "https://koigaura-coffeeroast.com/",
    "platform": "BASE",
    "address": "宮崎県串間市大納2608-1",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://koigaura.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('131560097', '恋ヶ浦ブレンド', 200, 'ブレンド', None),
    ('101170993', 'ブラジル プレミアムショコラ', 200, None, None),
    ('101173086', 'ブラジルサントスNo.2/S18', 200, None, None),
    ('101173568', 'コロンビア クレオパトラ', 200, None, None),
    ('101189164', 'グアテマラ ブルーレイクアテトラン', 200, None, None),
    ('101189919', 'エチオピア モカイルガチェフ Wote Konga(ウォンテ コンガ)2300', 200, None, None),
    ('101190663', 'ケニアAA', 200, None, None),
    ('101190908', 'マンデリンG1', 200, None, None),
    ('101190975', 'パプアニューギニア パラダイスプレミアム', 200, None, None),
    ('101288284', 'デカフェ・ドナネネン農園/スイスウォータープロセス', 200, None, None),
    ('95112188', '房総CAFEブレンド', 200, 'ブレンド', None),
    ('101278766', 'ハレの日cafeブレンド', 200, 'ブレンド', None),
    ('101253257', 'ダークブラウニー', 200, 'ブレンド', '深煎り'),
    ('101279559', 'エッセンシャル', 200, 'ブレンド', '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'101170993': 'ブラジル', '101173086': 'ブラジル', '101173568': 'コロンビア', '101189164': 'グアテマラ', '101189919': 'エチオピア', '101190663': 'ケニア', '101190908': 'インドネシア', '101190975': 'パプアニューギニア', '101288284': 'ブラジル'}

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
        time.sleep(5)  # BASEの429対策(アクセス間隔を空ける)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_koigauracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_koigauracoffee.json に出力しました")


if __name__ == "__main__":
    main()
