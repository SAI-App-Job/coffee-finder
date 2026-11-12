# -*- coding: utf-8 -*-
"""
scrape_fukucoffeeishigaki.py

福珈琲(https://fukucoffee.base.shop/、沖縄県石垣市大浜518-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
沖縄県・鹿児島県離島の再調査(2026-11)で発見。京都の「fuku coffee roastery」(scrape_fukucoffee.py)とは別店。

【対象商品について】
実データ確認済み(2026-10時点): 豆は4銘柄(各200g/400gの2サイズ)。同一銘柄が200g/400gの別商品として並ぶため、最小重量の200gを代表とする(400gは除外)。
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
    "name": "福珈琲",
    "url": "https://fukucoffee.base.shop/",
    "platform": "BASE",
    "address": "沖縄県石垣市大浜518-1",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": '福珈琲(https://fukucoffee.base.shop/)の商品ページ・about・特商法(/law)を2026-11-02に確認。食べログ(https://tabelog.com/okinawa/A4705/A470501/47028869/)で石垣市大浜518-1のカフェとして掲載。BASEにお知らせ日付はなく更新時期は不明。',
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://fukucoffee.base.shop"
REQUEST_INTERVAL = 5  # BASEは5秒以上空ける
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('74870744', 'エチオピア イルガチェフェG1 ナチュラル', 200, None, None),
    ('75212236', 'グアテマラ アンティグア SHB', 200, None, '深煎り'),
    ('75212278', 'グアテマラ オリエンテ ナチュラル', 200, None, None),
    ('75212313', 'マンデリン ビンタンリマ', 200, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
LD_DESC_PATTERN = re.compile(r'"description":("(?:[^"\\]|\\.)*")')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    ld_m = LD_DESC_PATTERN.search(html_text)
    if ld_m:
        ld = re.sub(r"\s+", " ", json.loads(ld_m.group(1))).strip()
        if len(ld) > len(desc or ""):
            desc = ld[:400]  # og:descriptionが店名のみ等で短い店舗があるため、JSON-LDの説明を優先する
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
    for n, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if n:
            time.sleep(REQUEST_INTERVAL)
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
    with open("data_fukucoffeeishigaki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukucoffeeishigaki.json に出力しました")


if __name__ == "__main__":
    main()
