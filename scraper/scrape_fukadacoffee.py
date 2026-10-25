# -*- coding: utf-8 -*-
"""
scrape_fukadacoffee.py

深田珈琲 犬山焙煎所(https://fukadacoffe.thebase.in/、愛知県犬山市大字犬山西古券23番 犬山ぐーまる内)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛知県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全22商品のうちコーヒー豆12銘柄。同一銘柄が複数規格で並ぶ場合は小さい方を代表とし(ケニアAA・エルインヘルトは100g、エスメラルダ・ゲイシャは試飲用12gではなく70g)、ドリップバッグ・ギフトセット・器具は除外。コスタリカ・カンデリージャは秋のセールで+30g増量中の150g価格。
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
    "name": "深田珈琲 犬山焙煎所",
    "url": "https://fukadacoffe.thebase.in/",
    "platform": "BASE",
    "address": "愛知県犬山市大字犬山西古券23番 犬山ぐーまる内",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE https://fukadacoffe.thebase.in/about(「店頭で丁寧に自家焙煎しています」「犬山に移転することで焙煎所、豆の販売…が一体」、犬山市犬山西古券23番 犬山ぐーまる内)と全商品を2026-10-20に確認。BASE特商法の住所と一致",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://fukadacoffe.thebase.in"
REQUEST_INTERVAL = 5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('854604', 'エスメラルダ・ゲイシャ・プライベートコレクション エルヴェロ地区', 70, None, None),
    ('69242737', 'コロンビア・カウカ・キングスマウンテン', 150, None, None),
    ('60068811', 'ダークローストブレンド', 150, 'ブレンド', None),
    ('65759267', '城下町ブレンド', 150, 'ブレンド', None),
    ('11430915', 'ケニア・ニエリ・カラティナ AA', 100, None, None),
    ('25984088', 'ブラジル・ブルボンアマレロ・アルコイリス農園', 150, None, None),
    ('11930066', 'グアテマラ・フィラデルフィア農園・ゲイシャ', 100, None, None),
    ('7807104', 'グアテマラ・フロレンシア農園・ゲイシャ', 100, None, None),
    ('7807109', 'コスタリカ・カンデリージャ・ハニー', 150, None, None),
    ('236983', 'グアテマラ エルインヘルト トラディショナル', 100, None, None),
    ('241211', 'イルガチェフェ・ウォルカ・FW', 150, None, None),
    ('1093314', 'イルガチェフェ・コンガ・ナチュラル', 150, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'7807109': 'コスタリカ', '1093314': 'エチオピア', '241211': 'エチオピア', '854604': 'パナマ'}

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
    with open("data_fukadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukadacoffee.json に出力しました")


if __name__ == "__main__":
    main()
