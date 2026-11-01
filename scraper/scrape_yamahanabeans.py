# -*- coding: utf-8 -*-
"""
scrape_yamahanabeans.py

コーヒーロースト山鼻Beans(https://beans502.thebase.in/、北海道札幌市中央区南23条西9丁目3-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
北海道の未登録・自家焙煎店の発掘調査(2026-10-26)で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全37商品が自家焙煎コーヒー豆(注文後焙煎。生豆240gを焙煎する単一サイズ展開で、器具・ドリップ・ギフト等の非豆商品は無し)。種類は「豆のまま/粉に挽く」を選択でき価格は同一。焙煎深度は購入者が備考欄で指定する方式のため焙煎度は商品情報に無く、焙煎後の重量も表記が無いため重量は不明(None)とする。
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
    "name": "コーヒーロースト山鼻Beans",
    "url": "https://beans502.thebase.in/",
    "platform": "BASE",
    "address": "北海道札幌市中央区南23条西9丁目3-1",
    "prefecture": "北海道",
    "source_note": "BASEショップ(https://beans502.thebase.in/)のabout・サイトマップ・各商品ページを2026-10-26に確認。住所は食べログ(tabelog.com/hokkaido/A0101/A010104/1057680/)と公式サイトで確認(実店舗あり)",
    "last_verified_at": "2026-10-26",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://beans502.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('160637967', '【数量限定】エチオピア ハラーG3 ナチュラル メルカバロ', None, None, None),
    ('160637977', '【数量限定】メキシコ ヘラクレス', None, None, None),
    ('13303004', '【数量限定】エチオピア ゲイシャG-1 ナチュラル カルマチェ農園', None, None, None),
    ('11768076', 'モカイルガチャフェ（エチオピア）', None, None, None),
    ('11768863', 'モカシダモ（エチオピア）', None, None, None),
    ('13685869', 'ブルーマウンテン№1（ジャマイカ）', None, None, None),
    ('13687190', 'ハワイコナ（アメリカ・ハワイ）', None, None, None),
    ('83089086', 'クラシックマヤ（ガテマラ）', None, None, None),
    ('11767776', 'ブルーレイク アテトラン（ガテマラ）', None, None, None),
    ('11768974', 'アンティグア パストレス ピーベリー（ガテマラ）', None, None, None),
    ('98488139', 'ガテマラSHB', None, None, None),
    ('9279755', 'プレミアムショコラ（ブラジル）', None, None, None),
    ('71442098', 'ブルボンピーベリー（ブラジル）', None, None, None),
    ('11745007', 'アマレロブルボン（ブラジル）', None, None, None),
    ('98486994', 'ブラジルサントス', None, None, None),
    ('11769003', 'ケニアAA', None, None, None),
    ('11767698', 'エーデルワイス（タンザニア）', None, None, None),
    ('98489290', 'タンザニア キリマンジャロ', None, None, None),
    ('12820243', 'マンデリントバコ ナチュラル（インドネシア）', None, None, None),
    ('11768002', 'ゴールデンマンデリン（インドネシア）', None, None, None),
    ('44654176', 'マンデリン G-1（インドネシア）', None, None, None),
    ('67527289', 'アイフプレミアム（東ティモール）', None, None, None),
    ('11760030', 'エメラルドマウンテン（コロンビア）', None, None, None),
    ('11758528', 'クレオパトラ（コロンビア）', None, None, None),
    ('98484866', 'コロンビアスプレモ', None, None, None),
    ('12168656', 'コーラルマウンテン（コスタリカ）', None, None, None),
    ('99120761', 'クラシックマルカラ【ホンジュラス】', None, None, None),
    ('11768992', 'パラダイスプレミアム（パプアニューギニア）', None, None, None),
    ('129021945', '【数量限定・カフェインレスコーヒー】インドネシア マンデリン クィーンスマトラ', None, 'デカフェ', None),
    ('26819749', '【カフェインレスコーヒー】メキシコデカフェ（オーガニック）', None, 'デカフェ', None),
    ('65095523', 'ブルーマウンテンブレンド', None, 'ブレンド', None),
    ('129236889', 'モカブレンド', None, 'ブレンド', None),
    ('25249311', '珈琲日和', None, 'ブレンド', None),
    ('17740160', '雪解けブレンド', None, 'ブレンド', None),
    ('14314725', '夢 〜北の大地で育んだ夢〜', None, 'ブレンド', None),
    ('16635066', 'バレンタインブレンド♡', None, 'ブレンド', None),
    ('98474461', '山鼻ブレンド', None, 'ブレンド', None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    time.sleep(5)  # BASE: リクエスト間隔5秒以上
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
    with open("data_yamahanabeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamahanabeans.json に出力しました")


if __name__ == "__main__":
    main()
