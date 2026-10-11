# -*- coding: utf-8 -*-
"""
scrape_yirgacoffeeroasters.py

YIRGA COFFEE ROASTERS(https://plough.theshop.jp/、岡山県岡山市北区弓之町)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全62商品のうち、100gで販売される豆27種を対象とする。同一銘柄が100g/200g(一部50g)で別ページ登録されているため、100gを代表として収録した。ドリップバッグ・水出しバッグのサブスク・器具・雑貨は除外。焙煎度は商品名の表記を採用。住所はBASE社の所在地が特商法に表示されるため使わず、公式のAboutページの沿革(2023年12月 弓之町にてオープン)から町名までとした。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルに重量・販売情報が含まれる、または重量違いの別ページ登録があるため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "YIRGA COFFEE ROASTERS",
    "url": "https://plough.theshop.jp/",
    "platform": "BASE",
    "address": "岡山県岡山市北区弓之町",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://plough.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('156592172', 'Brazil Stefano Um / Boram Um - Pink Bourbon - Natural 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('155847414', '中国 雲南 アナエロビックファーメンテーション ナチュラル 浅煎り-Light Roast-', 100, 'ストレート', '浅煎り'),
    ('152925854', 'ニカラグア - ラ・エスペランサ – ウォッシュド 浅煎り - Light Roast-', 100, 'ストレート', '浅煎り'),
    ('150012715', 'ニカラグア - ラベンディシオン・ファミリーエステート マラカツーラ カーボニックマセレーションナチュラル 浅煎り-Light Roast-', 100, 'ストレート', '浅煎り'),
    ('149933644', '【NCRC2026 焙煎大会 第2位受賞豆】 エル・カンバラチェ マラカツーラ ハニー（浅煎り）', 100, 'ストレート', '浅煎り'),
    ('149003335', 'Furure Coffee Farm - Toiさんのアラビカ Winey-Natural 浅煎り-Light Roast-', 100, 'ストレート', '浅煎り'),
    ('149001869', 'Furure Coffee Farm - Toiさんのアラビカ Winey-Honey 浅煎り-Light Roast-', 100, 'ストレート', '浅煎り'),
    ('146728805', 'COLOMBIA - EL SILENCIO OMBLIGON Yeast Fermentation Washed 浅煎り - Light Roast-', 100, 'ストレート', '浅煎り'),
    ('145390409', 'ブラジル スルデミナス スイートヒルズ ナチュラル 中煎り -HIGH ROAST-', 100, 'ストレート', '中煎り'),
    ('139386486', 'Brazil - Fazenda Guariroba Topazio Citrus Double Anaerobic Fermentation Black Honey 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('135379286', 'Colombia Finca SAZA Geisha Washed 浅煎り -Light Roast- JHDC2026 予選使用豆', 100, 'ストレート', '浅煎り'),
    ('135054880', 'Kenya Kii Washed 浅煎り-Light Roast-', 100, 'ストレート', '浅煎り'),
    ('134747358', 'エチオピア シダモG1ベンサ ニグセ シャンタウェネ ナチュラル Medium Roast-中浅煎り-', 100, 'ストレート', '中浅煎り'),
    ('132180349', 'グアテマラ ゴールデンパレンシア リオ コロラド農園SHB City Roast -中深煎り-', 100, 'ストレート', '中深煎り'),
    ('131091069', 'Rwanda - Nyarusiza AF05 CWS Washed 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('131090737', 'Rwanda - Dukundekawa Ruli Lot 1504 Soil Project Washed 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('124818327', 'パプアニューギニア コルブラン農園 ウォッシュ A 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('124195675', 'コロンビア ラス・アギラス シドラ 浅煎り -Light Roast -', 100, 'ストレート', '浅煎り'),
    ('124646937', 'エチオピア イルガチェフェ ゲルシ G1 ナチュラル 浅煎り Light Roast', 100, 'ストレート', '浅煎り'),
    ('124421211', 'ブラジル ダテーラ農園 OGAWA PLOT アララ ナチュラル 中煎り -High Roast-', 100, 'ストレート', '中煎り'),
    ('120083705', 'エチオピア イルガチェフィG1チェルチェレ ナチュラル 中深煎り -Fullcity Roast-', 100, 'ストレート', '中深煎り'),
    ('114939051', 'コロンビア ナリーニョ ゲイシャブレンド "ラ・アブエラ” 浅煎り -Light Roast-', 100, 'ストレート', '浅煎り'),
    ('112339129', 'エチオピア グジG2 ナチュラル 99.9％ デカフェ 中浅煎り -Medium Roast-', 100, 'ストレート', '中浅煎り'),
    ('111101070', 'エチオピア イルガチェフェ ゲルシ G2 ウォッシュド 浅煎り Light Roast', 100, 'ストレート', '浅煎り'),
    ('109159010', '中深煎り Future coffee farm チャムニム区画 ToiさんのロブスタNatural Full-Acidity(2024/2025ニュークロップ)', 100, 'ストレート', '中深煎り'),
    ('109209627', '中深煎り Future coffee farm チャムニム区画 ToiさんのロブスタRed-Honey', 100, 'ストレート', '中深煎り'),
    ('109200056', '中深煎り Future coffee farm Toiさんのロブスタ Winey-Natural(2024/2025ニュークロップ)', 100, 'ストレート', '中深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'156592172': 'ブラジル',
 '155847414': '中国',
 '152925854': 'ニカラグア',
 '150012715': 'ニカラグア',
 '149933644': 'ニカラグア',
 '149003335': 'ベトナム',
 '149001869': 'ベトナム',
 '146728805': 'コロンビア',
 '145390409': 'ブラジル',
 '139386486': 'ブラジル',
 '135379286': 'コロンビア',
 '135054880': 'ケニア',
 '134747358': 'エチオピア',
 '132180349': 'グアテマラ',
 '131091069': 'ルワンダ',
 '131090737': 'ルワンダ',
 '124818327': 'パプアニューギニア',
 '124195675': 'コロンビア',
 '124646937': 'エチオピア',
 '124421211': 'ブラジル',
 '120083705': 'エチオピア',
 '114939051': 'コロンビア',
 '112339129': 'エチオピア',
 '111101070': 'エチオピア',
 '109159010': 'ベトナム',
 '109209627': 'ベトナム',
 '109200056': 'ベトナム'}

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
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yirgacoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yirgacoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
