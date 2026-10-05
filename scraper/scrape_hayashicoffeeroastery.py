# -*- coding: utf-8 -*-
"""
scrape_hayashicoffeeroastery.py

HAYASHI COFFEE ROASTERY(https://coffeeh.base.shop/、京都府京都市山科区東野舞台町12-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全38商品のうち、飲み比べセット・ギフト・ドリップバッグ・水出しパックと、豆でないアーモンド2商品(ノンパレル・マルコナ)を除いた豆27商品(100g、内容量は生豆時質量)。焙煎度は購入時に選択式のため、商品ページ記載の「オススメ」焙煎度を採用した。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
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
    "name": "HAYASHI COFFEE ROASTERY",
    "url": "https://coffeeh.base.shop/",
    "platform": "BASE",
    "address": "京都府京都市山科区東野舞台町12-1",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeeh.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('160601659', 'コロンビアSP カフェインレス', 100, None, 'ハイロースト'),
    ('41496884', 'ハワイコナ Fancy ハワイアンクイーンコーヒー農園 ウォッシュド', 100, None, 'ハイロースト'),
    ('41496931', 'ブルーマウンテンNo.1 ブルーマウンテン地区 ウォッシュド', 100, None, 'ハイロースト'),
    ('67020918', 'イルガチェフェG1 ナチュラル アメデラロ', 100, None, 'ハイロースト'),
    ('128227104', 'サントゥアリオ農園 RASPBERRY アナエロビック', 100, None, 'ハイロースト'),
    ('42423763', 'ゲイシャ ゲシャビレッジ農園 チャカ ナチュラル', 100, None, 'ハイロースト'),
    ('50665054', 'VIVA LA VIDA アディトゥラン ウォッシュド', 100, None, 'シティロースト'),
    ('41496727', 'JOKER ナリーニョ ラウニオン ウォッシュド', 100, None, 'ハイロースト'),
    ('42835819', 'GOULALA エルメラ レテフォホ ウォッシュド', 100, None, 'ハイロースト'),
    ('56583805', 'ハウスブレンド 翡翠-カワセミ-', 100, 'ブレンド', 'シティロースト'),
    ('72659532', 'ダークブレンド・アオサギ', 100, 'ブレンド', 'フルシティロースト'),
    ('75879792', 'ファンタジー ブジラ ブルボン ナチュラル', 100, None, 'ハイロースト'),
    ('52388406', '季節のブレンド・秋', 100, 'ブレンド', 'シティロースト'),
    ('91098349', 'キリマンジャロ ンゴロンゴロAA ウォッシュド', 100, None, 'ハイロースト'),
    ('75879898', 'ORANGE SUNSHINE アナエロビック', 100, None, 'ハイロースト'),
    ('68744967', 'コマヤグア ブエノスアイレス プロジェクトゼロ ウォッシュド', 100, None, 'ハイロースト'),
    ('52876188', 'ヘレフG1 ボナズリア ウォッシュド', 100, None, 'ハイロースト'),
    ('46181084', 'アフリカンムーン レッド ルヴェンゾリ ナチュラル', 100, None, 'シティロースト'),
    ('42424553', 'マンデリン ブルーバタック スマトラ', 100, None, 'フルシティロースト'),
    ('42424079', 'レッドコンドル ウォッシュド', 100, None, 'ハイロースト'),
    ('42836713', 'SEVENTH HEAVEN ポアプス ビオダイナミック ナチュラル', 100, None, 'シティロースト'),
    ('41637518', 'セサルメルード バラオナ -LIMITED- ナチュラル', 100, None, 'ハイロースト'),
    ('42837536', 'ブルボンアマレロ アルコイリス農園 ハニー', 100, None, 'シティロースト'),
    ('53997113', 'エル・ボスケ農園 アナエロビック', 100, None, 'ハイロースト'),
    ('48942054', 'バリ神山 カフェインレス ウォッシュド', 100, None, 'ハイロースト'),
    ('52372094', 'プーアルピーチ 雲南 アナエロビック', 100, None, 'ハイロースト'),
    ('48944305', 'KYOTO農園 ウォッシュド', 100, None, 'シティロースト'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'160601659': 'コロンビア', '41496884': 'アメリカ(ハワイ)', '41496931': 'ジャマイカ', '67020918': 'エチオピア', '128227104': 'コロンビア', '42423763': 'エチオピア', '50665054': 'グアテマラ', '41496727': 'コロンビア', '42835819': '東ティモール', '75879792': 'ブルンジ', '91098349': 'タンザニア', '75879898': 'ミャンマー', '68744967': 'ホンジュラス', '52876188': 'エチオピア', '46181084': 'ウガンダ', '42424553': 'インドネシア', '42424079': 'ペルー', '42836713': 'インド', '41637518': 'ドミニカ共和国', '42837536': 'ブラジル', '53997113': 'ニカラグア', '48942054': 'インドネシア', '52372094': '中国', '48944305': 'コロンビア'}

# 商品ページ上は一部の選択肢のみ在庫なし(partially_purchasable)だが、豆の選択肢が在庫なしのため完売扱いにする商品ID
SOLD_OUT_IDS = set()

# 焙煎度の補足(ITEMSの焙煎度が店側の「おすすめ」表記で、購入時に選択できる場合など)
ROAST_HINT = '店のおすすめ焙煎度(購入時にシナモン〜フレンチから選択可能)'

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
    sold_out = (bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable") or item_id in SOLD_OUT_IDS

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
        "roast_hint": ROAST_HINT if (roast_level and ROAST_HINT) else None,
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
    with open("data_hayashicoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hayashicoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
