# -*- coding: utf-8 -*-
"""
scrape_moeka.py

自家焙煎珈琲 萌香(https://mocha.base.ec/、福岡県筑紫野市古賀906-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福岡県)のモール出店・独自EC調査で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全15商品のうち自家焙煎のコーヒー豆12銘柄(150g、ブレンド2種含む)。ドリップバッグ2点・ギフト用箱代は除外。焙煎度はBASEのカテゴリ(浅煎り/中煎り/中深煎り/深煎り)と商品説明に基づく(2カテゴリに載る商品は中間値/深め側を採用)。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトル表記とは別に、分類・焙煎度を確認して補っている)。
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
    "name": "自家焙煎珈琲 萌香",
    "url": "https://mocha.base.ec/",
    "platform": "BASE",
    "address": "福岡県筑紫野市古賀906-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": '販売先BASE(https://mocha.base.ec/)の全商品とカテゴリ(焙煎度別)を2026-10-20に確認。公式サイト https://www.coffeemocha.biz/ に実店舗(福岡県筑紫野市古賀906-1、喫茶・プロバット焙煎機による自家焙煎)の記載あり。ウォーカープラス等でも喫茶店・自家焙煎を確認。ブログは2026-07-31付まで更新。',
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://mocha.base.ec"
REQUEST_INTERVAL = 5  # BASEは5秒以上の間隔を空ける
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('149317170', 'ケニア・カンゴチョAA', 150, None, '中深煎り'),
    ('135239333', 'コロンビア・スイートベリー', 150, None, '中深煎り'),
    ('128282557', 'エルサルバドル・シベリア農園レッドブルボン・ナチュラル', 150, None, '中浅煎り'),
    ('128281728', 'グァテマラ・ラ・クプラ農園・ブルボン', 150, None, '中深煎り'),
    ('1109049', 'マイルドブレンド', 150, 'ブレンド', '中煎り'),
    ('27944621', 'モカ・イルガチェフェ・ナチュラル・G1', 150, None, '浅煎り'),
    ('27966652', 'モカ・イルガチェフェ・ウォッシュドG1', 150, None, '中煎り'),
    ('27966930', 'ブラジル・カフェビーニョ', 150, None, '中煎り'),
    ('40771994', 'モカ・イルガチェフェ・ナチュラル・G1<深煎り>', 150, None, '深煎り'),
    ('27884725', 'フレンチローストブレンド', 150, 'ブレンド', '深煎り'),
    ('27981986', 'マンデリン', 150, None, '深煎り'),
    ('62763820', 'エチオピア・グジ・ゲイシャジャスミンG1・ナチュラル', 150, None, '浅煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'27966930': 'ブラジル'}

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
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_moeka.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_moeka.json に出力しました")


if __name__ == "__main__":
    main()
