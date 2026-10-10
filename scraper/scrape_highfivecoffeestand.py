# -*- coding: utf-8 -*-
"""
scrape_highfivecoffeestand.py

High-Five COFFEE STAND(https://highfive0801.thebase.in/、長野県松本市深志3-1-3 1階)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(長野県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全57商品のうち、珈琲豆13商品(ブレンド2・シングル11)を対象とする。ドリップバッグ・ディップ式・グッズ・器具・書籍・Tシャツ・キャンドル、およびココナッツ/バナナ/グレープのインフューズドを使用するシーズナルブレンド2種(Dance Dande Dande・TROPIS)は除外した(エルパライソ ライチロットは発酵によるフレーバーでインフューズドではない旨が商品説明にあるため収録)。重量は商品ごと(200g中心、一部100g・50g)の単位で、エルインヘルト パカマラのみ50g。
商品名・重量・焙煎度・産地は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名に焙煎度・重量・キャッチコピーが混在するため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
商品ID一覧は トップページ・sitemap.xml の /items/<ID> から収集した。

【robots.txtについて】
他のBASE系店舗と同様、識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "High-Five COFFEE STAND",
    "url": "https://highfive0801.thebase.in/",
    "platform": "BASE",
    "address": "長野県松本市深志3-1-3 1階",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://highfive0801.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# id: 商品ID / name: 商品名 / weight: 重量(g) / roast_level: 焙煎度(粗い区分) / roast_hint: 原文の焙煎度表記
# origin: 産地(商品名から判定できない場合のみ明示) / blend: ブレンドの産地内訳 / category: 分類の上書き
ITEMS = [{'id': '111833884',
  'name': 'グアテマラ ガルデニア農園 Anaerobic Natural',
  'weight': 200,
  'roast_level': '中煎り',
  'roast_hint': 'High Roast（中煎り）',
  'origin': 'グアテマラ',
  'process': '嫌気性発酵ナチュラル'},
 {'id': '156222373', 'name': 'メキシコ チアパス チャンジュル農園 Washed', 'weight': 200, 'roast_level': '中深煎り', 'roast_hint': 'Full City Roast（中深煎）', 'origin': 'メキシコ'},
 {'id': '156029102', 'name': 'ウガンダ Mt.エルゴン カプチョルワW.S. Black Honey', 'weight': 200, 'roast_level': '中深煎り', 'roast_hint': 'City Roast(中深煎)', 'origin': 'ウガンダ'},
 {'id': '153947589', 'name': 'エチオピア グジG1 “ラスタ” Fully Washed', 'weight': 200, 'roast_level': '浅煎り', 'roast_hint': 'Medium Roast（浅煎)', 'origin': 'エチオピア'},
 {'id': '23737722',
  'name': 'HAYATE BLEND ハヤテブレンド',
  'weight': 200,
  'roast_level': '中深煎り',
  'roast_hint': 'シティロースト（中深煎）',
  'category': 'ブレンド',
  'blend': ['コロンビア', 'エチオピア', 'グアテマラ', 'ニカラグア']},
 {'id': '153948022', 'name': 'タンザニア エーデルワイス農園ケント種 Natural', 'weight': 200, 'roast_level': '中深煎り', 'roast_hint': 'Full City Roast(中深煎)', 'origin': 'タンザニア'},
 {'id': '152980514', 'name': 'グアテマラ エルインヘルト農園 Patagonia パカマラ Natural', 'weight': 50, 'roast_level': '浅煎り', 'roast_hint': 'Light Roast', 'origin': 'グアテマラ'},
 {'id': '152978190', 'name': 'パナマ ドンぺぺ農園 トレジャーマウンテン1898 Washed', 'weight': 200, 'roast_level': '中煎り', 'roast_hint': 'Medium~High Roast', 'origin': 'パナマ'},
 {'id': '153101368', 'name': 'ルワンダ Baho Coffee フムレW.S. Washed', 'weight': 200, 'roast_level': '中煎り', 'roast_hint': 'High Roast', 'origin': 'ルワンダ'},
 {'id': '153380857', 'name': 'パプアニューギニア パラダイスブルー Washed', 'weight': 200, 'roast_level': '中深煎り', 'roast_hint': 'City Roast（中深煎）', 'origin': 'パプアニューギニア'},
 {'id': '144001064',
  'name': 'コロンビア エルパライソ農園ライチロット Anaerobic Washed+Thermal Shock',
  'weight': 100,
  'roast_level': '浅煎り',
  'roast_hint': 'Medium Roast（浅煎）',
  'origin': 'コロンビア'},
 {'id': '4822969', 'name': 'コロンビア South Huila SUPREMO Washed', 'weight': 200, 'roast_level': '深煎り', 'roast_hint': 'French Roast（深煎）', 'origin': 'コロンビア'},
 {'id': '125093432',
  'name': 'シーズナルブレンド楓 KAEDE',
  'weight': 200,
  'roast_level': None,
  'roast_hint': None,
  'category': 'ブレンド',
  'blend': ['コロンビア', 'グアテマラ', 'エチオピア', 'ニカラグア']}]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item: dict) -> dict | None:
    item_id = item["id"]
    name = item["name"]
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
    if item.get("category"):
        parsed["category"] = item["category"]
    blend_components = []
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        blend_components = [{"origin_country": c} for c in item.get("blend", [])]
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item.get("origin"):
            parsed["origin_country"] = item["origin"]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": item.get("process") or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": item.get("roast_level"),
        "roast_hint": item.get("roast_hint"),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": item["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: id={item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_highfivecoffeestand.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_highfivecoffeestand.json に出力しました")


if __name__ == "__main__":
    main()
