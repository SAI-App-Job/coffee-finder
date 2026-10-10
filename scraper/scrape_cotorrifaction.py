# -*- coding: utf-8 -*-
"""
scrape_cotorrifaction.py

Cotorrifaction(https://cotorri.base.shop/、長野県塩尻市大門79-14)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(長野県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全39商品のうち、ドリップバッグ・水出しバッグ・ギフトセット・インフューズドコーヒー(髙波)を除いた100gのコーヒー豆17商品(ブレンド3・シングル12・デカフェ2)を対象とする。カワセミ/ペンギンブレンドはコールドブリュー用にブレンドした豆(ドリップでも可)で、豆100gの商品のため収録した。焙煎度違いのBrazil Sakura Bourbonは別商品として両方収録。
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
    "name": "Cotorrifaction",
    "url": "https://cotorri.base.shop/",
    "platform": "BASE",
    "address": "長野県塩尻市大門79-14",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cotorri.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# id: 商品ID / name: 商品名 / weight: 重量(g) / roast_level: 焙煎度(粗い区分) / roast_hint: 原文の焙煎度表記
# origin: 産地(商品名から判定できない場合のみ明示) / blend: ブレンドの産地内訳 / category: 分類の上書き
ITEMS = [{'id': '106380281', 'name': 'ペルショワールブレンド', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り～深煎り', 'category': 'ブレンド', 'blend': ['ブラジル', 'グアテマラ']},
 {'id': '134967395', 'name': 'Brazil Dolce Chocolada Natural No2 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '100187643', 'name': 'Brazil Tomio Fukuda DOT 深煎り', 'weight': 100, 'roast_level': '深煎り', 'roast_hint': '深煎り'},
 {'id': '136926124', 'name': 'Brazil Sakura Bourbon 中煎り', 'weight': 100, 'roast_level': '中煎り', 'roast_hint': '中煎り'},
 {'id': '102667084', 'name': 'Brazil Sakura Bourbon 深煎り', 'weight': 100, 'roast_level': '深煎り', 'roast_hint': '深煎り'},
 {'id': '144968403', 'name': 'Colombia Huila Las Moras Anaerobic Washed Excelso EP 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '100013501', 'name': 'Guatemala Genuine Antigua “Jasmine” 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '100013003', 'name': 'Guatemala Antigua Retana 中煎り', 'weight': 100, 'roast_level': '中煎り', 'roast_hint': '中煎り'},
 {'id': '151162454', 'name': 'Indonesia Kerinci Mountain Kopi Jeruk 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '142665898', 'name': 'Kenya Simba Washed AB TOP 深煎り', 'weight': 100, 'roast_level': '深煎り', 'roast_hint': '深煎り'},
 {'id': '107526829', 'name': 'Myanmar Phe No Pa Natural 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '100188012', 'name': 'Tanzania Edelweiss AA 中煎り', 'weight': 100, 'roast_level': '中煎り', 'roast_hint': '中煎り'},
 {'id': '100187843', 'name': 'Yemen Mokha Mattari 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '151180133', 'name': 'DECAF Colombia Tolima El Vino Washed Excelso EP 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '102836585', 'name': 'DECAF Costa Rica Jaguar Honey 中深煎り', 'weight': 100, 'roast_level': '中深煎り', 'roast_hint': '中深煎り'},
 {'id': '108903148',
  'name': 'カワセミブレンド',
  'weight': 100,
  'roast_level': '中煎り',
  'roast_hint': '華やか中煎りベース(コールドブリュー用ブレンド)',
  'category': 'ブレンド',
  'blend': ['ブラジル', 'エチオピア', 'ミャンマー']},
 {'id': '108979795',
  'name': 'ペンギンブレンド',
  'weight': 100,
  'roast_level': '深煎り',
  'roast_hint': 'コクの深煎りベース(コールドブリュー用ブレンド)',
  'category': 'ブレンド',
  'blend': ['ブラジル', 'イエメン']}]

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
    with open("data_cotorrifaction.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cotorrifaction.json に出力しました")


if __name__ == "__main__":
    main()
