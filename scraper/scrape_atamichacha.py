# -*- coding: utf-8 -*-
"""
scrape_atamichacha.py

熱海 coffee house 茶々(https://atamichacha.base.shop/、静岡県熱海市清水町11-11)の商品情報を取得する。BASE(atamichacha.base.shop)。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全16商品のうち、100gの焙煎豆7点(スペシャルティ単一産地5点+貫一ブレンド・お宮ブレンド)を対象とする。ドリップパック・ギフトセット・水出しアイスコーヒーは除外。
商品名・重量・焙煎度・精製方法は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
住所は特定商取引法表記(/law)の「静岡県熱海市清水町11-11」を確認(個人事業主の所在地=店舗所在地)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "熱海 coffee house 茶々",
    "url": "https://atamichacha.base.shop/",
    "platform": "BASE",
    "address": "静岡県熱海市清水町11-11",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://atamichacha.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定),
#  精製方法(Noneなら商品名から判定), 産地の上書き(Noneなら商品名から判定))
ITEMS = [
    ('144594620', 'コロンビア ウィラ 有機栽培 スペシャルティコーヒー', 100, None, '中煎り', 'ウォッシュド', None),
    ('144594443', 'タンザニアAA スノートップ スペシャルティコーヒー', 100, None, '中煎り', 'ウォッシュド', None),
    ('144594245', 'グァテマラ サンタロッサ スペシャルティコーヒー', 100, None, '中煎り', 'ウォッシュド', None),
    ('144593987', 'ブラジル トミオフクダ ドライオンツリー スペシャルティコーヒー', 100, None, '中煎り', None, None),
    ('144768180', 'ハイチ フレンチブルー', 100, None, '中煎り', 'ウォッシュド', None),
    ('28682025', '貫一ブレンド(深煎り)', 100, 'ブレンド', '深煎り', None, None),
    ('28682125', 'お宮ブレンド(浅煎り)', 100, 'ブレンド', '浅煎り', None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level, process, origin) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        import html as _html
        desc = re.sub(r"\s+", " ", _html.unescape(desc_m.group(1))).strip()[:400] or None
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
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "product_description"
    if process:
        parsed["processing_method"] = normalize_processing_method(process)

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
    for item in ITEMS:
        try:
            record = build_record(*item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_atamichacha.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_atamichacha.json に出力しました")


if __name__ == "__main__":
    main()
