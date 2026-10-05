# -*- coding: utf-8 -*-
"""
scrape_buntcoffee.py

BUNT COFFEE(https://buntcoffee.thebase.in/、愛知県安城市福釜町釜ヶ渕2-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛知県)の新規発掘で発見。住所は/law(特定商取引法に基づく表記)で確認済み。

【対象商品について】
実データ確認済み(2026-10時点): 全25商品のうち、ドリップバッグ・水出しバッグ・アソートセット・グッズを除いた豆12銘柄(ブレンド4・ストレート8。デカフェ1含む)。パナマ ゲイシャのみ50g(最小重量)で販売、他は100g。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description、無い場合は商品説明欄)は商品ページから取得する。
在庫は item_purchasability が unpurchasable の場合のみ品切れとし、一部バリエーションのみ
在庫切れ(partially_purchasable)の場合は販売中として扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BUNT COFFEE",
    "url": "https://buntcoffee.thebase.in/",
    "platform": "BASE",
    "address": "愛知県安城市福釜町釜ヶ渕2-1",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://buntcoffee.thebase.in"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('160783340', 'Mexico Decaf Chiapas organic', 100, None, 'ミディアムロースト'),
    ('160782638', 'AUTUMN BLEND 2026', 100, None, '中煎り'),
    ('160782355', 'Indonesia mandheling Alur Badak', 100, None, None),
    ('160781653', 'Honduras El Jardin anaerobic natural', 100, None, 'ライトロースト'),
    ('151758790', '【New 】アメリカンブレンド', 100, None, '中煎り'),
    ('21902042', 'Ethiopia aricha natural G-1', 100, None, 'ライトロースト'),
    ('58946052', 'Ethiopia chelbesa natural organic', 100, None, 'ライトロースト'),
    ('119783802', 'Guatemala Fraijanes SHB', 100, None, None),
    ('21901953', 'Brazil tomio fukuda bourbon', 100, None, '中煎り'),
    ('21881714', 'BUNT BLEND', 100, None, '中煎り'),
    ('73934866', 'クラシカルビターブレンド', 100, None, '深煎り'),
    ('126036727', 'パナマ タラマンカス農園ゲイシャ', 50, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
DESC_FALLBACK_PATTERN = re.compile(r'<div class="itemDescription">(.*?)</div>', re.S)
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PRICE_FALLBACK_PATTERN = re.compile(r"'itemPrice':\s*(\d+)")
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def extract_description(html_text: str) -> str | None:
    m = DESC_PATTERN.search(html_text)
    if m:
        text = html_lib.unescape(m.group(1))
    else:
        m = DESC_FALLBACK_PATTERN.search(html_text)
        if not m:
            return None
        text = html_lib.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    text = re.sub(r"\s+", " ", text).strip()[:400]
    return text or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc = extract_description(html_text)
    price_m = PRICE_PATTERN.search(html_text) or PRICE_FALLBACK_PATTERN.search(html_text)
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
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_buntcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_buntcoffee.json に出力しました")


if __name__ == "__main__":
    main()
