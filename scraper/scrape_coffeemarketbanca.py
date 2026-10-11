# -*- coding: utf-8 -*-
"""
scrape_coffeemarketbanca.py

coffee market banca(http://www.coffee-banca.jp/、岡山県岡山市北区野田3丁目22番3号)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全92商品のうち、ブレンド16種・ストレート18種の豆商品を対象とする。ドリップバッグ・水出しパック・リキッドアイスコーヒー・生豆・保存缶・セット、およびレターパック対応の重複登録(同一銘柄の発送方法違い)は除外した。多くは200g入りで、ブラジル2種(カップオブ・プログレッシブセラード優勝ロット)のみ100g入り。焙煎度は商品説明の表記(「中深煎り」等)を採用し、表記のない商品はnullとした。なお「ばんこく珈琲 津山」とは別法人(有限会社ばんこく珈琲 岡山市北区野田)。
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
    "name": "coffee market banca",
    "url": "http://www.coffee-banca.jp/",
    "platform": "BASE",
    "address": "岡山県岡山市北区野田3丁目22番3号",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "http://www.coffee-banca.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('78963483', '【Banca中煎りブレンドA】（スペシャルブレンド）', 200, 'ブレンド', '中煎り'),
    ('79000760', 'Ice Coffee Blend 【ビター】', 200, 'ブレンド', '深煎り'),
    ('78969348', '【ESPRESSO Bitters & rich blend】 (10th ICT 2018 金賞)', 200, 'ブレンド', '深煎り'),
    ('127789427', '【2026年限定ブレンド『馬』】', 200, 'ブレンド', '中深煎り'),
    ('78969004', 'ヘビー【深煎りブレンド】', 200, 'ブレンド', '深煎り'),
    ('78969092', '【Banca中煎りブレンドB】(ベーシック)', 200, 'ブレンド', '中煎り'),
    ('78969206', '【ロイヤルブレンド】', 200, 'ブレンド', None),
    ('78973043', 'ストロング【深煎りブレンド】', 200, 'ブレンド', '深煎り'),
    ('78974007', 'Ice Coffee Blend 【マイルド】', 200, 'ブレンド', '深煎り'),
    ('79000887', 'ESPRESSOブレンド【クラシック】', 200, 'ブレンド', '深煎り'),
    ('79017547', 'ブルボンブレンド【中深煎り】', 200, 'ブレンド', '中深煎り'),
    ('79018242', '【ブルーマウンテンブレンド】', 200, 'ブレンド', None),
    ('79018363', 'ライトブレンド【浅煎り】', 200, 'ブレンド', '浅煎り'),
    ('79021814', 'おかやま珈琲物語【鬼の涙】', 200, 'ブレンド', None),
    ('79021876', 'おかやま珈琲物語【桃太郎の雫】', 200, 'ブレンド', None),
    ('79150783', 'カフェインレス【ブレンド】', 200, 'ブレンド', '中煎り'),
    ('79150114', '【エメラルドマウンテン】', 200, None, '中深煎り'),
    ('83769079', '【ブラジル ナチュラル】', 100, None, '浅煎り'),
    ('146221737', '【ブラジル ウォッシュド】', 100, None, '中煎り'),
    ('82151457', '【コスタリカ ホワイトハニー】', 200, None, '中煎り'),
    ('79150039', '【ブルーマウンテンNo１】', 200, None, '中煎り'),
    ('79150191', '【マンデリン】', 200, None, '深煎り'),
    ('79150224', '【エチオピア モカ】', 200, None, '中煎り'),
    ('79150276', '【アンデスマウンテン】', 200, None, '中深煎り'),
    ('79150332', '【キリマンジャロ】', 200, None, '中深煎り'),
    ('79150389', '【グアテマラ アンティグア】', 200, None, '中深煎り'),
    ('79150419', '【グアテマラ】', 200, None, '中深煎り'),
    ('79150466', '【コロンビア ブルボン】', 200, None, '中深煎り'),
    ('79150513', '【東ティモール】', 200, None, '浅煎り'),
    ('79150560', '【ペルー】', 200, None, '中煎り'),
    ('146287872', '【ドミニカ バラオナ】', 200, None, '中煎り'),
    ('79150635', 'カフェインレス【ブラジル】', 200, None, '中煎り'),
    ('79150659', 'カフェインレス【コロンビア】', 200, None, '中煎り'),
    ('79150713', 'カフェインレス【エチオピア】', 200, None, '中煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'79150114': 'コロンビア',
 '83769079': 'ブラジル',
 '146221737': 'ブラジル',
 '82151457': 'コスタリカ',
 '79150039': 'ジャマイカ',
 '79150191': 'インドネシア',
 '79150224': 'エチオピア',
 '79150276': 'エクアドル',
 '79150332': 'タンザニア',
 '79150389': 'グアテマラ',
 '79150419': 'グアテマラ',
 '79150466': 'コロンビア',
 '79150513': '東ティモール',
 '79150560': 'ペルー',
 '146287872': 'ドミニカ共和国',
 '79150635': 'ブラジル',
 '79150659': 'コロンビア',
 '79150713': 'エチオピア'}

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
    with open("data_coffeemarketbanca.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeemarketbanca.json に出力しました")


if __name__ == "__main__":
    main()
