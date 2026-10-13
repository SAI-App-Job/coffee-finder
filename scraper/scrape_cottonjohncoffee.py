# -*- coding: utf-8 -*-
"""
scrape_cottonjohncoffee.py

cotton john coffee(https://cottonjohn.official.ec/、愛媛県松山市由良町1166)の商品情報を取得する。BASE独自ドメイン。

【店舗発見の経緯】
全国再調査(愛媛県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): サイトマップ43商品のうち、豆100g 10銘柄を収録(同一銘柄で100g/200g・豆/粉の別商品があるため、最小重量100gの豆を代表に採用)。ブラジル カフェサウダージ アルタ モジアナはfull cityとFrenchの焙煎違い2商品を別銘柄として収録。除外: 200g商品・粉商品・Tシャツ・CAP・注意書きページ。焙煎度は商品説明の【焙煎度】欄に従って明示。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが容量表記・キャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

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
    "name": "cotton john coffee",
    "url": "https://cottonjohn.official.ec/",
    "platform": "BASE",
    "address": "愛媛県松山市由良町1166",
    "prefecture": "愛媛県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cottonjohn.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('123887817', 'グアテマラ プリマベーラ', 100, None, '中深煎り'),
    ('121151362', 'メキシコ フィンカ ラ チャンジュル', 100, None, '中深煎り'),
    ('120486234', 'インドネシア マンデリン ガヨマウンテン', 100, None, '深煎り'),
    ('100337488', 'パプアニューギニア ネビリエール バレー/ ナチュラル', 100, None, '深煎り'),
    ('24441066', '東ティモール マウベシ農協', 100, None, '中深煎り'),
    ('78155206', 'ブラジル シティオ・ダ・トーレ農園', 100, None, '中深煎り'),
    ('62749451', 'ブラジル カフェサウダージ アルタ モジアナ full cityroast', 100, None, '深煎り'),
    ('49287295', 'コロンビア デカフェ ピオネロス ラバド', 100, None, '深煎り'),
    ('62756595', 'ブラジル カフェサウダージ アルタ モジアナ French roast', 100, None, '極深煎り'),
    ('31736505', 'エチオピア モカ シャキッソG1 ナチュラル medium roast', 100, None, '浅煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'31736505': 'エチオピア'}

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
        "roast_level": roast_level,  # 商品名の「ハイブリッド」等がハイロースト誤検出されるため、明示値のみ採用
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
    with open("data_cottonjohncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cottonjohncoffee.json に出力しました")


if __name__ == "__main__":
    main()
