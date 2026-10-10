# -*- coding: utf-8 -*-
"""
scrape_reconfortcafe.py

カフェ レコンフォール(https://reconfort.theshop.jp/、三重県四日市市堀木2-13-2-2)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(三重県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全71商品のうち、100g(生豆時)ページ31種を代表とする(250gの重複ページ、ティーバッグ式・ドリップバッグ・リキッド・フィルターは除外)。商品名の「生豆時100g」は焙煎前の生豆重量の表記だが、重量は100gとして記録した。注文後に焙煎。
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
    "name": "カフェ レコンフォール",
    "url": "https://reconfort.theshop.jp/",
    "platform": "BASE",
    "address": "三重県四日市市堀木2-13-2-2",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://reconfort.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('139823973', 'パプアニューギニア コルブラン農園 アルーシャ', 100, None, None),
    ('139090307', 'ルワンダ ガツィボ レッドブルボン', 100, None, None),
    ('139088677', 'エルサルバドル ビスタ・エルモサ農園 ナチュラル', 100, None, None),
    ('139088096', 'エチオピア イルガチェフ G1 ウォッシュド', 100, None, None),
    ('121275958', 'タンザニア キリマンジャロ ブルカ農園 AA KIBO', 100, None, None),
    ('121274897', 'エチオピア シャキッソ モルドコフ農園 G1 ナチュラル', 100, None, None),
    ('121273241', 'ペルー クスケーニャ スペシャル', 100, None, None),
    ('64368786', 'ブラジル ドナ・ネネン農園 フルッタ・メルカドン', 100, None, None),
    ('41353941', 'ミャンマー ジーニアス・シャンハイランド ウォッシュド', 100, None, None),
    ('84826083', 'ロングボトムブレンド', 100, 'ブレンド', None),
    ('79839575', '円頓寺ブレンド', 100, 'ブレンド', None),
    ('74770295', 'ケニア エンカイ AA TOP', 100, None, None),
    ('41353745', 'グアテマラ オリエンテ ナチュラル', 100, None, None),
    ('40765058', 'プレミアムブレンド', 100, 'ブレンド', None),
    ('41350621', '四日市こにゅうどうくんブレンド', 100, 'ブレンド', None),
    ('41351918', 'No.117ブレンド', 100, 'ブレンド', None),
    ('41352201', 'ブルーマウンテンブレンド', 100, 'ブレンド', None),
    ('41352376', 'モカスウィートブレンド', 100, 'ブレンド', None),
    ('41352440', 'エスプレッソブレンド', 100, 'ブレンド', None),
    ('41352839', 'ボンボンブレンド', 100, 'ブレンド', None),
    ('41352888', 'アイスコーヒーブレンド', 100, 'ブレンド', None),
    ('41353006', 'デカフェブレンド', 100, 'ブレンド', None),
    ('41353270', 'ブラジル ピーベリーショコラーチ', 100, None, None),
    ('41353352', 'コロンビア エメラルドマウンテン', 100, None, None),
    ('41353449', 'コロンビア アルヘンティーナ スウィート&フラワーズ', 100, None, None),
    ('41353664', 'グアテマラ アンティグア SHB', 100, None, None),
    ('41353827', 'インドネシア スラウェシ タナ・トラジャ', 100, None, None),
    ('41353877', 'インドネシア マンデリン リントン・ニ・フタ G1', 100, None, None),
    ('41354045', 'インド モンスーン マラバール AA', 100, None, None),
    ('42340479', 'ジャマイカ ブルーマウンテン No.1', 100, None, None),
    ('72234131', 'インドネシア ロブスタ G1', 100, None, None),
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

    # 名前の誤検出を除く: 「シャンハイランド」の「ハイ」を焙煎度(ハイロースト)と誤認、
    # 「No.117ブレンド」の「No.117」をグレードと誤認するため
    if item_id == "41353941" and not roast_level:
        parsed["roast_level"] = None
    if parsed["category"] == "ブレンド":
        parsed["grade"] = None

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
    with open("data_reconfortcafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_reconfortcafe.json に出力しました")


if __name__ == "__main__":
    main()
