# -*- coding: utf-8 -*-
"""
scrape_cafedreamnishinomiya.py

珈琲屋ドリーム(https://cafedream.thebase.in/、兵庫県西宮市甲風園1-12-12)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-26時点): BASE全7商品のうち、自家焙煎コーヒー豆の3銘柄(ブレンド2・ストレート1)。200g(豆のまま/粉の選択式)。ギフトセット2点とドリップパック2点は除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する(取得間隔5秒)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
/cart/・/shops/等のみ禁止で商品ページは許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲屋ドリーム",
    "url": "https://cafedream.thebase.in/",
    "platform": "BASE",
    "address": "兵庫県西宮市甲風園1-12-12",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-10-26確認。python-requests/curl等は個別にDisallow、User-agent: *は/cart/・/shops/等のみ禁止。識別可能なUser-Agentを使用)",
    "source_note": "販売先(通販ページ) https://cafedream.thebase.in/ のトップ・各商品ページ・特商法(/law)・ABOUT(/about)を2026-10-26に確認。住所は特商法の記載(有限会社ホソミコーヒー)と食べログ・Yahoo!マップ・神戸新聞で一致。焙煎度は商品ページに記載なし(roast_level未設定)。更新日付の表示はない",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://cafedream.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('17403440', 'カフェドリーム', 200, 'ブレンド', None),
    ('17404602', 'フレンチブレンド', 200, 'ブレンド', None),
    ('17443587', 'グアテマラ・アティトラン・ブルーレイク', 200, 'ストレート', None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {'17443587': 'グアテマラ'}

DESC_CUT = None
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        raw = desc_m.group(1).replace("&amp;", "&")
        if DESC_CUT and DESC_CUT in raw:
            raw = raw.split(DESC_CUT)[0]
        desc = re.sub(r"\s+", " ", raw).strip()[:400] or None
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
    with open("data_cafedreamnishinomiya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafedreamnishinomiya.json に出力しました")


if __name__ == "__main__":
    main()
