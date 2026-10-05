# -*- coding: utf-8 -*-
"""
scrape_pocchicoffee.py

Coffee shop POCCHI 京都洛北 珈琲豆焙煎所(https://pocchicoffee.base.shop/、京都府京都市左京区)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全81商品のうち、100g/200gが別ページで並ぶ豆を100gの代表で収録した30銘柄(デカフェ多数)。セット・ドリップ・水出し・キャニスター缶に加え、フルーツ香料を付けた「インフューズドコーヒー」(ストロベリー・ピーチハニー・ライチハニー・グレープ・ミルキーメロン)はフレーバー系として除外した。焙煎度は各ページの種類選択の先頭(既定)の焙煎度。複数焙煎度を選べる商品(中煎り/深煎り)は先頭のものを採用した。住所は/law(BASE社の所在地)でなくABOUTページの「京都市左京区 洛北エリア」までしか確認できない。
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
    "name": "Coffee shop POCCHI 京都洛北 珈琲豆焙煎所",
    "url": "https://pocchicoffee.base.shop/",
    "platform": "BASE",
    "address": "京都府京都市左京区",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://pocchicoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('158688143', 'デカフェ ペルー ウォッシュ G1 （有機栽培）', 100, None, '中煎り'),
    ('158687400', 'デカフェ ブラジル 4/5 マウンテンウォーター ナチュラル', 100, None, '中深煎り'),
    ('156127876', 'おつきさまブレンド', 100, 'ブレンド', '深煎り'),
    ('128895923', 'のんびりぽっちブレンド', 100, 'ブレンド', '中深煎り'),
    ('149897757', 'デカフェ コロンビア サンタンデール ラプラデーラ農園＆コーカフェ ウォッシュ（有機栽培）', 100, None, '中深煎り'),
    ('143649352', 'デカフェ メキシコ ドンラファ（有機栽培）', 100, None, '深煎り'),
    ('116063273', 'ブラジル ビスタアレグレ農園 パイナップル ハニー ナチュラル No.2', 100, None, '中煎り'),
    ('139562857', 'エルサルバドル プエルト アルトゥロ農園 マイクロロット ナチュラル SHG', 100, None, '中深煎り'),
    ('139559785', 'イエメン モカマタリ フルーツショコラタ（有機栽培コーヒー）', 100, None, '中煎り'),
    ('116634954', 'こころぽかぽかブレンド', 100, 'ブレンド', '中深煎り'),
    ('116063943', 'ブラジル ドルチェ チョコラーダ', 100, None, '中深煎り'),
    ('116634533', 'カフェオレぽっちブレンド', 100, 'ブレンド', '中深煎り'),
    ('121804750', 'ベトナム アラビカ ラムドン省 ミンマウンテン フリーウォッシュ G1', 100, None, '中深煎り'),
    ('121708648', 'ミャンマー ジーニアス ハニー（有機栽培）', 100, None, '中煎り'),
    ('119182306', 'パナマ エル・パロマール農園 ゲイシャ ナチュラル SHB', 100, None, None),
    ('116377408', 'メキシコ マヤビニック（有機栽培）', 100, None, '中煎り'),
    ('115353865', 'コスタリカ ジャガーハニー', 100, None, '中煎り'),
    ('116067258', 'グアテマラ アンティグア ドラド イエローブルボン ウォッシュ SHB', 100, None, '中煎り'),
    ('116069420', 'インドネシア リントン マンデリン パタックブルー', 100, None, '中煎り'),
    ('116278891', 'ペルー カハマルカ フリーウォッシュ G1 （有機栽培）', 100, None, '中煎り'),
    ('116282773', 'コロンビア シエラネバダ ラ・ミエル ウォッシュ スプレモ（有機栽培）', 100, None, '中煎り'),
    ('116291203', 'エチオピア イルガチェフェ ナチュラルG1 チェルベサ（有機栽培）', 100, None, '中煎り'),
    ('116294795', 'パナマ ボケテ バホモノ農園 ウォッシュ', 100, None, '中煎り'),
    ('116296469', 'エチオピア イルガチェフェ イディド GRADE2 ウォッシュド（有機栽培）', 100, None, '中煎り'),
    ('116628963', '中国 雲南 プーアル かもめの天空農園 ナチュラル ダブルファーメンテーション', 100, None, '中煎り'),
    ('116362114', 'デカフェ エチオピア シダモ G2 ウォッシュ（有機栽培）', 100, None, '中煎り'),
    ('116376390', 'デカフェ メキシコ マヤビニック（有機栽培）', 100, None, '中煎り'),
    ('116830775', 'エスプレッソぽっちブレンド', 100, 'ブレンド', '深煎り'),
    ('133530373', 'ケニア シンバ ウォッシュ AB TOP', 100, None, '深煎り'),
    ('133532651', 'ペルー アンデスブルー ウォッシュ G1', 100, None, '中煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'116628963': '中国'}

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
    with open("data_pocchicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pocchicoffee.json に出力しました")


if __name__ == "__main__":
    main()
