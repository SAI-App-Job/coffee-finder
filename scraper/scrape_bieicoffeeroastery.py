# -*- coding: utf-8 -*-
"""
scrape_bieicoffeeroastery.py

美瑛珈琲ロースタリー(https://bieicoffee.base.shop、北海道上川郡美瑛町美馬牛新栄(新栄の丘。番地は公式・観光協会とも非掲載))の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(北海道)の新規発掘で発見。

【店舗情報の根拠(2026-10-26確認)】
公式 https://bieicoffee.base.shop/about 「自家焙煎珈琲ショップがオープンし今年で3年目」「店舗内で珈琲豆の販売も行っております」(店舗営業は5月から11月初旬、豆の販売は通年)。
美瑛町観光協会 https://www.biei-hokkaido.jp/ja/facility/bieicoffee-cafe 「新栄の丘で自家焙煎珈琲ショップをオープン」(住所は美馬牛新栄まで、営業9:30-15:30・火水定休)。
BASE特商法の所在地はBASE社住所のため店舗住所の根拠にしない。

【対象商品について】
実データ確認済み(2026-10-26時点): 全7商品がコーヒー豆。ゲイシャ2種は100g、その他5種は200g(クリックポスト発送用)。いずれも豆/粉の選択で、豆の価格を採用。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html as htmllib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "美瑛珈琲ロースタリー",
    "url": "https://bieicoffee.base.shop/",
    "platform": "BASE",
    "address": "北海道上川郡美瑛町美馬牛新栄(新栄の丘。番地は公式・観光協会とも非掲載)",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://bieicoffee.base.shop/ の全7商品(sitemap)を2026-10-26に確認。店舗番地は公式・観光協会とも非掲載のため町内の地名(美馬牛新栄)まで。実店舗の営業は5月〜11月初旬のみ(豆の通販は通年)。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://bieicoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度, 焙煎度の補足(roast_hint))
ITEMS = [
    ('160415197', 'グアテマラ', 200, None, '中煎り', 'Medium Roast'),
    ('116360794', 'ブラジル', 200, None, '中煎り', 'Medium Roast'),
    ('104689546', 'タンザニア', 200, None, '中深煎り', 'City Roast'),
    ('104689358', 'インドネシア', 200, None, '深煎り', 'Dark Roast'),
    ('104689420', 'エチオピア', 200, None, '浅煎り', 'Light Roast'),
    ('157892782', 'エチオピア ゲイシャ', 100, None, '浅煎り', 'Light Roast'),
    ('157771316', 'パナマ ゲイシャ', 100, None, '浅煎り', 'Light Roast'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}
EXTRA_TAGS = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_desc(text: str) -> str:
    text = re.sub(r"\s+", " ", htmllib.unescape(text)).strip()
    # 共通の定型文(注文後焙煎の案内・賞味期限・送料)を除いて味の説明を残す
    text = re.sub(r"^注文を受けてから焙煎しますので.*?お楽しみ下さい。\s*", "", text)
    text = re.sub(r"賞味期限.*$", "", text).strip()
    return text[:400]


def build_record(item_id, name, weight_g, category_override, roast_level, roast_hint):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = clean_desc(desc_m.group(1)) if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # partially_purchasable = 粉のみ在庫なし等の一部バリエーション在庫切れ。豆が買えるため販売中扱い
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

    tags = list(parsed["post_processing_tags"])
    for t in EXTRA_TAGS.get(item_id, []):
        if t not in tags:
            tags.append(t)

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
        "post_processing_tags": tags,
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, roast_hint in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, roast_hint)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL_SEC)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bieicoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bieicoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
