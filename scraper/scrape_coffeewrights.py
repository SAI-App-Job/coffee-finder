# -*- coding: utf-8 -*-
"""
scrape_coffeewrights.py

Coffee Wrights(https://store.coffee-wrights.jp/、東京都台東区蔵前4-20-2)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASEの特定商取引法表記(/law)で台東区蔵前4-20-2の所在地、aboutページで蔵前のロースタリー&カフェ(ほか表参道にカフェ)であることを確認(2店舗)。全49商品のうち、同一豆が【50g/100g/200g/500g/1kg】で別ページ登録されているものは最小サイズのみを採り、ドリップバッグ・定期便・テイスティングセット・コールドブリューバッグ・テストロースト・ラッピングを除く13銘柄(ブレンド1、デカフェ1含む)を対象とする。完売中の商品も完売として収録する。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名に重量・焙煎度・キャッチコピーが混在しているため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
在庫がpartially_purchasable(豆のみ品切れ等)の商品は販売中として扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Coffee Wrights",
    "url": "https://store.coffee-wrights.jp/",
    "platform": "BASE",
    "address": "東京都台東区蔵前4-20-2",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://store.coffee-wrights.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g。ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('159866408', 'エルサルバドル / Don Jaime "Pacamara" Anaerobic Natural', 100, None, None),
    ('158860414', 'エチオピア / Tamiru Tadesse "ALO" White Honey (2025 Origin Tour Limited Edition)', 50, None, None),
    ('156046810', 'ルワンダ / Nkara Lot.1004 "Soil Project" Washed', 100, None, None),
    ('154737523', 'エチオピア / Dimtu Washed', 100, None, None),
    ('151250726', 'ケニア / Gatura AA Washed', 100, None, None),
    ('149655313', 'エチオピア / Nigusse Gemeda "Morke" Slow Dry Natural', 200, None, None),
    ('148303687', 'コロンビア / Los Guayacanes "Chiroso" Washed', 200, None, None),
    ('147431950', 'エチオピア / Bona Sedaka Natural "Medium Roast"', 100, None, 'ミディアムロースト'),
    ('146771275', 'エルサルバドル / El Conacaste "Yellow Bourbon" Washed', 200, None, None),
    ('128268119', 'カフェインレス コロンビア / Tolima Cafe Grande "Decaf"', 100, None, None),
    ('112493079', 'ニカラグア / Casa Blanca DFPN Medium Roast', 100, None, 'ミディアムロースト'),
    ('90155181', 'エチオピア / TAMIRU TADESSE "ALO Berry" Natural 2022-2023 Crop', 100, None, None),
    ('27355136', 'アンペアブレンド / Guatemala + Brazil', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する(商品ID: 産地)
ORIGIN_OVERRIDES = {}

# 商品名の語から誤判定される/名称に記載がない精選方法を、商品ページの記載に合わせて上書きする(商品ID: 精選方法)
PROCESSING_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
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

    if item_id in PROCESSING_OVERRIDES:
        parsed["processing_method"] = PROCESSING_OVERRIDES[item_id]

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
    with open("data_coffeewrights.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeewrights.json に出力しました")


if __name__ == "__main__":
    main()
