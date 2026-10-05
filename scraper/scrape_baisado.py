# -*- coding: utf-8 -*-
"""
scrape_baisado.py

baisado(https://baisado.theshop.jp/、京都府京都市左京区下鴨西半木町28-4)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全43商品のうち、焙煎豆16銘柄(ブレンド6・ストレート9・デカフェ1。ブルーマウンテンのみ50g)。ドリップバッグ・水出しバッグ・リキッド・定期便・フィルター等の器具・黒豆茶、およびフレーバー系(ラム酒香る・ウイスキー香る・スパイスコーヒー)、100g×2の「イルガチェフェ デュオ」(2種セット扱い)を除いた。住所は/law(BASE社の所在地)ではなく公式サイト baisado.com のアクセスページで確認した。焙煎度は深煎りハウスブレンド以外は商品ページに個別記載が無くnull。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "baisado",
    "url": "https://baisado.theshop.jp/",
    "platform": "BASE",
    "address": "京都府京都市左京区下鴨西半木町28-4",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://baisado.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('83884223', 'ジャマイカ ブルーマウンテン No.1 クライズデール ティピカ', 50, None, None),
    ('146713698', 'エチオピア イルガチェフェ G1 コンガ Natural', 100, None, None),
    ('94387773', 'インドネシア マンデリン G1 "トバコ"', 100, None, None),
    ('155770999', 'エチオピア イルガチェフェ G1 ゲルシ Natural', 100, None, None),
    ('53494065', 'グアテマラ アンティグア SHB アゾテア農園', 100, None, None),
    ('53493822', 'ケニア AA TOP "マサイ"', 100, None, None),
    ('78704827', 'コロンビア マグダレーナ EX "パシオン デ ラ シエラ" ティピカ', 100, None, None),
    ('155335338', 'タンザニア ムビンガ AB "リヴィングストン"', 100, None, None),
    ('63227023', 'ブラジル セラード ヤマグチ農園 ブルボン Natural', 100, None, None),
    ('93707407', 'ペルー カハマルカ G1 "ナランハ"', 100, None, None),
    ('82906529', 'baisado ハウスブレンド(ブラジル・ケニア・コロンビア)', 100, 'ブレンド', None),
    ('136612798', '深煎りハウスブレンド(ブラジル・ケニア・コロンビア)', 100, 'ブレンド', '深煎り'),
    ('68201363', 'baisado 秋ブレンド(ケニア・コロンビア・ブラジル)', 100, 'ブレンド', None),
    ('88618247', 'baisado そうげんブレンド(エチオピア・グアテマラ・ペルー)', 100, 'ブレンド', None),
    ('78077167', 'baisado モカ・ジャバ(エチオピア・インドネシア)', 100, 'ブレンド', None),
    ('104275358', 'デカフェ(カフェインレス)ブラジル セラード ドナネネン農園 ブルボン Pulped Natural スイスウォータープロセス', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
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
        time.sleep(1.0)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_baisado.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisado.json に出力しました")


if __name__ == "__main__":
    main()
