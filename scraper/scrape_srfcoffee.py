# -*- coding: utf-8 -*-
"""
scrape_srfcoffee.py

西院 ROASTING FACTORY(https://srfcoffee.base.shop/、京都府京都市右京区西院日照町60-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全30商品のうち、店舗紹介・電動ミル・オーダーメイドドリップバッグを除き、ゲイシャ/スーダンルメは100gと200gの別ページのため100gを代表とした豆25商品。内容量は生豆時質量(焙煎後は80〜88%程度)で、焙煎度は購入時に選択式のためNone。RF Blended・サントスNo.2・SHB・ホンジュラスSHGは200g単位販売。
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
    "name": "西院 ROASTING FACTORY",
    "url": "https://srfcoffee.base.shop/",
    "platform": "BASE",
    "address": "京都府京都市右京区西院日照町60-1",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://srfcoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('113570503', 'コロンビア ファンマルティン農園 ゲイシャ ウォッシュド', 100, None, None),
    ('157604537', 'コロンビア ラ・ラハ農園 スーダンルメ ウォッシュド', 100, None, None),
    ('21245429', 'パナマ ラ・エスメラルダ農園 ダイヤモンド・マウンテン', 100, None, None),
    ('157604630', 'コロンビア ロス・ピノス農園 ピンクブルボン', 100, None, None),
    ('12733514', 'ブラジル トミオフクダ ドライオンツリー', 100, None, None),
    ('13297282', 'ブラジル サントアントニオ プレミアムショコラ', 100, None, None),
    ('127433301', 'コロンビア カウカ スプレモ', 100, None, None),
    ('22756894', 'グァテマラ アンティグア SHB アゾテア農園 ブルボン', 100, None, None),
    ('71886366', 'ペルー パープルコンドル ナチュラル', 100, None, None),
    ('84375199', 'ペルー オレンジコンドル ハニー', 100, None, None),
    ('138787031', '東ティモール レテフォホ ゴウララ集落 part2', 100, None, None),
    ('12732816', 'インドネシア マンデリン ビンタンリマ', 100, None, None),
    ('125003315', 'ケニア アダロニア AA', 100, None, None),
    ('80870781', 'タンザニア タリメ ゴールドマイン AA', 100, None, None),
    ('110475887', 'タイ サイアム・レッドムーン ナチュラル', 100, None, None),
    ('86806516', 'エチオピア ボナズリア ヘレフ ウォッシュド', 100, None, None),
    ('71297063', 'エチオピア ボナズリア ヘレフ ナチュラル', 100, None, None),
    ('97160590', 'ジンバブエ クレイクバレー農園 AA+', 100, None, None),
    ('141953319', 'ブラジル カフェ・ヴィーニョ', 100, None, None),
    ('20857558', 'エチオピア ゲシャ村 ケビルゲイシャ農園 ゲイシャ G1 ナチュラル', 100, None, None),
    ('153565449', 'ブラジル デカフェ ハンザウォーター処理', 100, None, None),
    ('12731830', 'RF Blended オリジナルブレンド', 200, 'ブレンド', None),
    ('12731863', 'ブラジル サントスNo.2', 200, None, None),
    ('12731880', 'グァテマラ SHB', 200, None, None),
    ('112985999', 'ホンジュラス SHG', 200, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'110475887': 'タイ', '138787031': '東ティモール', '153565449': 'ブラジル', '97160590': 'ジンバブエ'}

# 商品ページ上は一部の選択肢のみ在庫なし(partially_purchasable)だが、豆の選択肢が在庫なしのため完売扱いにする商品ID
SOLD_OUT_IDS = set()

# 焙煎度の補足(ITEMSの焙煎度が店側の「おすすめ」表記で、購入時に選択できる場合など)
ROAST_HINT = None

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
    with open("data_srfcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_srfcoffee.json に出力しました")


if __name__ == "__main__":
    main()
