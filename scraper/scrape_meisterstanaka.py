# -*- coding: utf-8 -*-
"""
scrape_meisterstanaka.py

マイスターズ・コーヒー TANAKA(https://www.coffee-world.jp/、福井県福井市城東4-11-23 玉冠ビル1F-4)
の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(福井県)の新規発掘。住所は /law(特定商取引法)と /about で確認(2026-10-12)。

【対象商品について】
実データ確認済み(2026-10-12): sitemap.xmlの商品69件のうち、コーヒー豆は同一銘柄が
「（100g）」「（200g）」の別商品として並ぶ。最小重量の100gを代表に採用する(23銘柄:
ストレート16・ブレンド7(デカフェ含む))。ドリップオン、リキッドアイスコーヒー、水出しパック、
ギフト、紅茶は除外。2026/10/1付の価格改定告知があるため、価格は商品ページの現行表示価格
(product:price:amount)を採用する。
商品名・重量・産地は、商品ページのタイトル/説明(「生産国：」等の表記)を確認したうえで
下のITEMSに明示している。価格・在庫(item_purchasability)・説明は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "マイスターズ・コーヒー TANAKA",
    "url": "https://www.coffee-world.jp/",
    "platform": "BASE",
    "address": "福井県福井市城東4丁目11-23 玉冠ビル1F-4",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.coffee-world.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("134293153", "まるちゃん〈ボリビア・ピーベリー〉", 100, None, None),
    ("91592668", "熟成珈琲 CROWN〈クラウン〉", 100, None, None),
    ("101158356", "ボリビア・アンデスマウンテン", 100, None, None),
    ("91592248", "ゴールデン・ペルー（グルメ・マイクロロット限定品）", 100, None, None),
    ("91881739", "森のめぐみ〈パプアニューギニア〉", 100, None, None),
    ("91880948", "香りの宝石箱・ドミニカ", 100, None, None),
    ("91881172", "じっくり天日乾燥・コスタリカ", 100, None, None),
    ("91881287", "ワンダフル・ケニア", 100, None, "シティロースト"),
    ("91883458", "マンデリン・トバ湖", 100, None, None),
    ("91881517", "コロンビア・スプレモ・マイスターセレクト", 100, None, None),
    ("91883619", "ブラジル・kanjuku", 100, None, None),
    ("91881632", "グァテマラ・エスペシャル", 100, None, None),
    ("91592842", "ブラックダイヤモンド", 100, None, "深煎り"),
    ("91883843", "キリマンジャロ・ブルートップAA", 100, None, None),
    ("91884423", "パナマ・ピカイチ・エスメラルダ農園（グルメ・マイクロロット限定品）", 100, None, None),
    ("91884135", "エチオピア・モカ イルガチェッフェ・グレード１", 100, None, None),
    ("91885177", "マイルド&リッチブレンド", 100, "ブレンド", None),
    ("91885483", "広く・深く 香るブレンド", 100, "ブレンド", None),
    ("91885698", "こんがり こうばしブレンド", 100, "ブレンド", None),
    ("91885778", "おとなの ちょいビターブレンド", 100, "ブレンド", None),
    ("91885965", "エスプレッソコーヒー・クレマクレマ", 100, "ブレンド", None),
    ("91886096", "カフェインレスコーヒー「夢見る珈琲」", 100, "ブレンド", None),
    ("91885065", "マイスター・プレステージブレンド", 100, "ブレンド", None),
]

# 説明の「生産国：」「原産国：」表記に基づく産地(coffee_parserの辞書で検出できないもの)
ORIGIN_OVERRIDES = {
    "134293153": "ボリビア",
    "101158356": "ボリビア",
    "91592842": "マラウイ",
    "91881739": "パプアニューギニア",
    "91883458": "インドネシア",
    "91881632": "グアテマラ",
    "91883843": "タンザニア",
    "91884135": "エチオピア",
    "91880948": "ドミニカ共和国",
    "91883619": "ブラジル",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    import html as _html
    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", _html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
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


def scrape_all_products():
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_meisterstanaka.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_meisterstanaka.json に出力しました")


if __name__ == "__main__":
    main()
