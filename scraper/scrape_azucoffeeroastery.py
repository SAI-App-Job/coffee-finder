# -*- coding: utf-8 -*-
"""
scrape_azucoffeeroastery.py

Azu.coffee roastery(https://azucoffee.base.shop/、島根県出雲市多伎町多岐157-1 キララ多伎西側テナント)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(島根県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-15時点): 全43商品(sitemap.xml)のうち、豆19銘柄(ストレート14・ブレンド5)を対象とする。多くは100g/200gが別ページ登録のため100gを代表とし、「通販限定」のマンデリングレード1とケニアAAは200gのみのため200gを採用。1kgジップ袋(事業者向け大容量)・定期便は除外。エチオピア・アベベ ゴダナ農園は深煎り/中煎りの別商品として両方収録。住所はBASE特商法(/law)で確認(〒699-0902)。焙煎度は商品名の【】表記による(ブレンドは「ややライト」等の表記のみで焙煎度名ではないため#6の極深煎り以外は未設定)。
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
    "name": "Azu.coffee roastery",
    "url": "https://azucoffee.base.shop/",
    "platform": "BASE",
    "address": "島根県出雲市多伎町多岐157-1 キララ多伎西側テナント",
    "prefecture": "島根県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://azucoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('75753995', 'インドネシア・マンデリン アチェ アルールバダ', 100, None, '深煎り'),
    ('133862902', 'ルワンダ・ジュル', 100, None, '深煎り'),
    ('152030120', 'ブルンジ・キビンゴCWS', 100, None, '深煎り'),
    ('76756159', 'ケニア・リアキベル ファクトリー', 100, None, '深煎り'),
    ('151159748', 'タンザニア・アカシアヒルズ農園', 100, None, '深煎り'),
    ('119313470', 'エチオピア・アベベ ゴダナ農園 深煎り', 100, None, '深煎り'),
    ('75658133', 'エチオピア・アベベ ゴダナ農園 中煎り', 100, None, '中煎り'),
    ('75657969', 'グアテマラ・エル ポトレロ農園', 100, None, '中深煎り'),
    ('97183605', 'ブラジル・レクレイオ農園イエローブルボン', 100, None, '中深煎り'),
    ('75658386', 'デカフェ メキシコ・チアパス', 100, None, '中深煎り'),
    ('155368492', 'ベトナム・アオザイ ハニー', 100, None, '中煎り'),
    ('120546981', 'エチオピア・シャンタウェネ', 100, None, '浅煎り'),
    ('102356346', 'Blend #2 ややライト', 100, None, ''),
    ('102356375', 'Blend #3 マイルド', 100, None, None),
    ('102356405', 'Blend #4 ビター', 100, None, None),
    ('102356442', 'Blend #5 しっかりビター', 100, None, None),
    ('145471245', 'Blend #6 極深煎り', 100, None, '極深煎り'),
    ('153375578', '通販限定 インドネシア・マンデリン grade1', 200, None, '深煎り'),
    ('153375625', '通販限定 ケニアAA', 200, None, '深煎り'),
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
        parsed["processing_method"] = None
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
        "roast_level": (None if roast_level == "" else (roast_level or parsed["roast_level"])),
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
    with open("data_azucoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_azucoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
