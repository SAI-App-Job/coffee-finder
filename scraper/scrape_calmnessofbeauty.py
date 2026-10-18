# -*- coding: utf-8 -*-
"""
scrape_calmnessofbeauty.py

Calmness of Beauty(https://cob.base.shop/、宮崎県宮崎市江平東町9-12 Lビル102号)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(宮崎県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの8商品(5銘柄)のうち、フィルターロースト3銘柄は100g、ダークロースト2銘柄は200gのみの
取り扱い。100gと200gの両方がある銘柄は100gを代表に採用。商品名の「Filter Roast」「Dark Roast」は
焙煎方針の表記で、ダークローストは深煎りとして扱う(フィルターローストは焙煎度の明示がないためnull、
roast_hintに表記を保持)。住所はBASE特商法(宮崎市江平東町9-12 Lビル102号)
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルに重量が【】で付記されているため)。
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
    "name": "Calmness of Beauty",
    "url": "https://cob.base.shop/",
    "platform": "BASE",
    "address": "宮崎県宮崎市江平東町9-12 Lビル102号",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cob.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("160037717", "El Injerto Bourbon (Guatemala) / Filter Roast", 100, None, None),
    ("142085129", "Terra Verde (Colombia) / Filter Roast", 100, None, None),
    ("138793143", "Takele Mammo (Ethiopia) / Filter Roast", 100, None, None),
    ("156022724", "Ouro Verde (Brazil) / Dark Roast", 200, None, "深煎り"),
    ("148975590", "La Folie (Guatemala) / Dark Roast", 200, None, "深煎り"),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {
    "160037717": "グアテマラ",
    "142085129": "コロンビア",
    "138793143": "エチオピア",
    "156022724": "ブラジル",
    "148975590": "グアテマラ",
}

PROCESS_PATTERN = re.compile(r"精製方法\s*[:：]\s*([^\s標※]+)")
PROCESS_MAP = {"フリーウォッシュド": "ウォッシュド", "ウォッシュド": "ウォッシュド", "ナチュラル": "ナチュラル"}

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

    pm = PROCESS_PATTERN.search(desc_m.group(1)) if desc_m else None
    if pm and not parsed["processing_method"]:
        parsed["processing_method"] = PROCESS_MAP.get(pm.group(1))
    roast_hint = "フィルターロースト" if "Filter Roast" in name else ("ダークロースト" if "Dark Roast" in name else None)

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
        "roast_hint": roast_hint,
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
        time.sleep(1)
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
    with open("data_calmnessofbeauty.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_calmnessofbeauty.json に出力しました")


if __name__ == "__main__":
    main()
