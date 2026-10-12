# -*- coding: utf-8 -*-
"""
scrape_yamanobaisen.py

山の焙煎所(https://yamanobaisen.official.ec/、@yamano_baisenjo、山梨県笛吹市一宮町)の商品情報を取得する。BASE。
住所は市区町村(一宮町)までを採用する。

【店舗発見の経緯】
全国再調査(山梨県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-12時点): 全46商品のうち、自家焙煎豆41銘柄を対象とする。
除外: DRIP SET(ドリップバッグ)、お試しお任せコーヒー(80g×4種セット)、コーヒー豆チョコレート(菓子)、
コロンビア サントゥアリオ農園のパッションフルーツ/ラズベリー カーボニックマセレーション2件
(果実モストと一緒に発酵させるインフューズド系)。
重量(g)と焙煎度: 内容量は静的HTMLにも商品説明(og:description/JSON-LD)にも記載がなく
(商品ページのバリエーションは焙煎度の選択のみで、グラム数の選択肢なし)、weight_g=Noneとした。
焙煎度は6段階(R-1〜R-6)から注文時にお客様が選ぶ方式で商品ごとの固定値がないため、roast_levelもNone。
価格は各商品ページの表示価格。在庫は item_purchasability(partially_purchasableは販売中扱い)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "山の焙煎所",
    "url": "https://yamanobaisen.official.ec/",
    "platform": "BASE",
    "address": "山梨県笛吹市一宮町",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://yamanobaisen.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('55114575', 'コロンビアSP カフェインレス', None, None, None),
    ('55117606', 'GOULALA 東ティモール エルメラ レテフォホ', None, None, None),
    ('55118142', 'JOKER コロンビア ナリーニョ ラウニオン', None, None, None),
    ('55119134', 'AFRICAN MOON JACKAL ウガンダ ルウェンゾリ', None, None, None),
    ('55165415', 'コスタリカ FSHB ジャガーハニー', None, None, None),
    ('55166491', 'ペルー レッドコンドル', None, None, None),
    ('55167256', 'ブラジル ブルボン アマレロ ラランハル農園', None, None, None),
    ('55171103', 'インドネシア スラウェシ ママサ', None, None, None),
    ('55188056', 'SEVENTH HEAVEN インド ポアブスビオダイナミック', None, None, None),
    ('55192606', 'ドミニカ ワイニープリンセサ アルフレド・ディアス農園', None, None, None),
    ('55192683', 'ミャンマーG1 星山スペシャルティ', None, None, None),
    ('55249235', 'パプアニューギニア AA シグリ', None, None, None),
    ('55275268', 'タイ チェンライ ドイパンコン', None, None, None),
    ('55280474', 'エルサルバドル サンタナ サンタマリア農園', None, None, None),
    ('55283341', 'インドネシア スマトラマンデリン G1', None, None, None),
    ('55452892', 'エチオピア イルガチェフェ G1 ゲデブ チェルベサ村 ウォッシュド', None, None, None),
    ('55453070', 'ブラジル カフェドルチェ', None, None, None),
    ('55453168', 'タンザニア キリマンジャロ ンゴロンゴロ AA コンゴニ農園', None, None, None),
    ('55453375', 'VIVA LA VIVA グアテマラ SHB ソロラ アティトゥラン パンポヒラ', None, None, None),
    ('70412919', 'ブラジル サントス ニブラ', None, None, None),
    ('69703985', 'インドネシア ロブスタ WIB/1 PTP', None, None, None),
    ('70413062', 'ブラジル ブルボン アマレロ アルコイルス農園', None, None, None),
    ('70416226', 'ケニア トマトレッド AA ガタイシファクトリー', None, None, None),
    ('70416360', 'ブラジル ハニーショコラ', None, None, None),
    ('70417565', 'ブラジル サントアントニオ ショコラ ピーベリー', None, None, None),
    ('70422140', 'エチオピア グジ ゲイシャ ジャスミンG1 ナチュラル', None, None, None),
    ('70423052', 'エチオピア グジ ゲイシャ ホワイトリリーG1 ウォッシュド', None, None, None),
    ('70423770', 'エチオピア モカ イルガチェフェG1 コチャレ 7Days アナエロビコ', None, None, None),
    ('70426958', 'グアテマラ オリエンテ ナチュラル', None, None, None),
    ('70432551', 'ORANGE SUNSHINE ミャンマー G1 シャン州 ピンダヤ村 アナエロビック', None, None, None),
    ('74389359', 'ルワンダ スカイヒル コプロカWS', None, None, None),
    ('74393067', 'コロンビア エルパライソ アナエアロビコ ライチ', None, None, None),
    ('74393156', 'ブラジル プラナウト農園 エスプレッソレディー', None, None, None),
    ('74830928', 'エチオピア シダモ カフェインレス マウンテンウォーター', None, None, None),
    ('95931441', 'ペルーアルパカ', None, None, None),
    ('97120728', 'メキシコ コアティ ウォッシュド', None, None, None),
    ('118306371', 'タンザニア サウステラ AA', None, None, None),
    ('118308044', 'ハイチ ブードゥーブルー', None, None, None),
    ('118310048', 'エチオピア モカ シダモ プライドオブ アルベゴナ ナチュラル', None, None, None),
    ('138175513', 'グアテマラ ゴールデンパレンシア リオ コロラド農園 SHB', None, None, None),
    ('150559741', 'インドネシア スマトラ マンデリン アチェ ルーサー パンタンカウカ農園', None, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'55117606': '東ティモール', '55192683': 'ミャンマー', '55275268': 'タイ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
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
        "roast_level": roast_level,  # 注文時に選択する方式のため商品名からは推定しない(「ハイチ」の誤検出防止)
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
    with open("data_yamanobaisen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamanobaisen.json に出力しました")


if __name__ == "__main__":
    main()
