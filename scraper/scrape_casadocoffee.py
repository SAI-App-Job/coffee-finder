# -*- coding: utf-8 -*-
"""
scrape_casadocoffee.py

Casa do Coffee(https://www.casadocoffee.com/、長野県北佐久郡御代田町草越1173-1871)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(長野県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全25商品のうち、ドリップバッグ・ギフト・お試しセット・ギフト箱を除いたコーヒー豆13商品(ブレンド3・シングル9・デカフェ1)を対象とする。ニカラグア アナエロビックナチュラルは旧ページ(中浅煎り・ID 100575642)が売り切れで新ページ(中深煎り・ID 155551860)へ誘導されているため新ページのみ収録。各商品は150g/300g/500gの重量選択式で、最小の150gの価格(product:price:amount)を代表とする。
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
    "name": "Casa do Coffee",
    "url": "https://www.casadocoffee.com/",
    "platform": "BASE",
    "address": "長野県北佐久郡御代田町草越1173-1871",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.casadocoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# id: 商品ID / name: 商品名 / weight: 重量(g) / roast_level: 焙煎度(粗い区分) / roast_hint: 原文の焙煎度表記
# origin: 産地(商品名から判定できない場合のみ明示) / blend: ブレンドの産地内訳 / category: 分類の上書き
ITEMS = [{'id': '155555546',
  'name': 'オータムブレンド2026',
  'weight': 150,
  'roast_level': '中深煎り',
  'roast_hint': 'アフターミックス（中深煎り）',
  'category': 'ブレンド',
  'blend': ['ニカラグア', 'ブラジル']},
 {'id': '55768914', 'name': 'やや深煎りブレンド', 'weight': 150, 'roast_level': '中深煎り', 'roast_hint': 'アフターミックス（中深煎り～深煎り程度）', 'category': 'ブレンド'},
 {'id': '51877715', 'name': 'マイルドブレンド', 'weight': 150, 'roast_level': '中煎り', 'roast_hint': 'アフターミックス（中煎り～中深煎り程度の豆）', 'category': 'ブレンド'},
 {'id': '110894210',
  'name': 'デカフェ：ブラジル カルモ・デ・ミナス レッドブルボン',
  'weight': 150,
  'roast_level': '中深煎り',
  'roast_hint': '中深煎り シティロースト程度',
  'origin': 'ブラジル',
  'process': 'ナチュラル'},
 {'id': '155551860', 'name': 'ニカラグア アナエロビックナチュラル 中深煎り', 'weight': 150, 'roast_level': '中深煎り', 'roast_hint': '中深煎り', 'origin': 'ニカラグア'},
 {'id': '141414130', 'name': 'コロンビア ピンクブルボン ダイナミックナチュラル', 'weight': 150, 'roast_level': '中煎り', 'roast_hint': '中煎り', 'origin': 'コロンビア'},
 {'id': '130268372', 'name': 'エチオピア ゲイシャ種ナチュラル', 'weight': 150, 'roast_level': '中浅煎り', 'roast_hint': '中浅〜中煎り', 'origin': 'エチオピア'},
 {'id': '95196771', 'name': 'エチオピア イルガチェフェナチュラル 深煎り', 'weight': 150, 'roast_level': '深煎り', 'roast_hint': '深煎り フルシティロースト～フレンチロースト程度', 'origin': 'エチオピア'},
 {'id': '51876101', 'name': 'ブラジル サントアントニオ プレミアムショコラ', 'weight': 150, 'roast_level': '中深煎り', 'roast_hint': '中深煎り シティロースト程度', 'origin': 'ブラジル'},
 {'id': '51876416', 'name': 'インドネシア マンデリン ビンタンリマ', 'weight': 150, 'roast_level': '中深煎り', 'roast_hint': '中深煎り～深煎り シティロースト～フルシティロースト程度', 'origin': 'インドネシア'},
 {'id': '116577363', 'name': 'グァテマラ アンティグア地区 ラ・タシータ農園 ウォッシュド', 'weight': 150, 'roast_level': '中浅煎り', 'roast_hint': '中浅煎り～中煎り', 'origin': 'グアテマラ'},
 {'id': '51875541', 'name': 'エチオピア イルガチャフィ ブナブナ ナチュラル', 'weight': 150, 'roast_level': '中浅煎り', 'roast_hint': '中浅煎り', 'origin': 'エチオピア'},
 {'id': '124782097', 'name': 'コスタリカ イエローハニー', 'weight': 150, 'roast_level': '中深煎り', 'roast_hint': '中煎り～中深煎り', 'origin': 'コスタリカ'}]

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
    with open("data_casadocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_casadocoffee.json に出力しました")


if __name__ == "__main__":
    main()
