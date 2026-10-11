# -*- coding: utf-8 -*-
"""
scrape_powerplantcoffee.py

パワープラントコーヒー(https://powerplant.theshop.jp/、岡山県倉敷市藤戸町天城1760-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全34商品のうち、100g単位で販売する豆24種(ブレンド14種・ストレート10種)を対象とする。100g×4袋のセット・ドリップバッグ・水出しコーヒーパック・オリーブオイルは除外した。価格は100g単位(商品説明に「金額は100g単位となります」と明記)。焙煎度は商品名の表記を採用。KURO・珈茶は産地の記載がなくオリジナルブレンドのセットに含まれるためブレンドとして扱った。公式サイト(powerplantcoffee.com)ではなくBASE系ショップ(powerplant.theshop.jp)から取得。
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
    "name": "パワープラントコーヒー",
    "url": "https://powerplant.theshop.jp/",
    "platform": "BASE",
    "address": "岡山県倉敷市藤戸町天城1760-1",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://powerplant.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('160639715', 'エチオピア グジG1 アナソラ ナチュラル 中煎り', 100, None, '中煎り'),
    ('53628204', '【期間限定】 ハロウィンブレンド 深煎り', 100, 'ブレンド', '深煎り'),
    ('26254311', '【季節限定】秋珈琲 中深煎り', 100, 'ブレンド', '中深煎り'),
    ('31452343', '珈茶 浅煎り', 100, 'ブレンド', '浅煎り'),
    ('22944849', '藤戸ブレンド 中煎り', 100, 'ブレンド', '中煎り'),
    ('23506569', '倉敷ブレンド 中煎り', 100, 'ブレンド', '中煎り'),
    ('23507450', '天城ブレンド 中深煎り', 100, 'ブレンド', '中深煎り'),
    ('23507469', '和 中深煎り', 100, 'ブレンド', '中深煎り'),
    ('23507430', 'パワーブレンド 深煎り', 100, 'ブレンド', '深煎り'),
    ('84541718', '祝ブレンド 中煎り', 100, 'ブレンド', '中煎り'),
    ('38437274', 'サンキューブレンド 中深煎り', 100, 'ブレンド', '中深煎り'),
    ('38437353', 'バースデイブレンド 中深煎り', 100, 'ブレンド', '中深煎り'),
    ('113487163', 'モカシダモG2 中煎り', 100, None, '中煎り'),
    ('59245937', 'コロンビア クレオパトラ 中煎り', 100, None, '中煎り'),
    ('23506664', 'デカフェ コロンビア 中煎り', 100, None, '中煎り'),
    ('64732122', 'マサマ キリマンジャロ 中煎り', 100, None, '中煎り'),
    ('23507334', 'ブラジル・ブルボン 中煎り', 100, None, '中煎り'),
    ('71910720', 'グアテマラ ウェウェテナンゴ 中深煎り', 100, None, '中深煎り'),
    ('23506593', '東ティモール 中深煎り', 100, None, '中深煎り'),
    ('23507289', 'ゴールデン マンデリン 中深煎り', 100, None, '中深煎り'),
    ('96412936', 'ケニア アフリカンシンフォニー 中深煎り', 100, None, '中深煎り'),
    ('23506689', 'アイスブレンド 深煎り', 100, 'ブレンド', '深煎り'),
    ('23506710', 'KURO 深煎り', 100, 'ブレンド', '深煎り'),
    ('45310117', 'オーレ 深煎り', 100, 'ブレンド', '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'160639715': 'エチオピア',
 '113487163': 'エチオピア',
 '59245937': 'コロンビア',
 '23506664': 'コロンビア',
 '64732122': 'タンザニア',
 '23507334': 'ブラジル',
 '71910720': 'グアテマラ',
 '23506593': '東ティモール',
 '23507289': 'インドネシア',
 '96412936': 'ケニア'}

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
    with open("data_powerplantcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_powerplantcoffee.json に出力しました")


if __name__ == "__main__":
    main()
