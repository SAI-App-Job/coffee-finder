# -*- coding: utf-8 -*-
"""
scrape_luontocoffee.py

LUONTOCOFFEE(luontocoffee.jpが情報サイト、実際の通販はluontocoffee.com、
愛知県岡崎市大和町塗御堂40-1、自家焙煎豆のオンライン販売)の商品情報を
取得する。WordPress+WooCommerce。公開Store API
(/wp-json/wc/store/v1/products)から認証不要で取得する(dots Coffee
Roasters・ひつじ珈琲と同じ方式)。

【ドメインについて】
実データ確認済み: luontocoffee.jp(タイトル「愛知でコーヒー豆の通販なら
LUONTOCOFFEE」)はSEO向けの情報サイトで、商品ページへのリンクは全て
luontocoffee.com側を指している。実店舗の所在地(愛知県岡崎市大和町塗御堂
40-1)はluontocoffee.com/about/ページの特定商取引法相当の記載で確認済み。

robots.txt確認済み(2026-09時点): 標準的なWordPressのrobots.txt
(/wp-admin/のみDisallow、admin-ajax.phpは個別にAllow)。本スクレイパーが
使うStore APIは制限対象外。

【重量について】
実データ確認済み: 対象商品はほぼ全て「100g or 200g」という表記で1商品
ページ内に2つの重量をWooCommerceのvariable product(バリエーション)として
持たせている(価格は100g側が基準)。商品名先頭に出現する重量表記
(WEIGHT_PATTERNの最初のマッチ)が常に最小の100gに対応するため、商品名から
直接weight_gを取得できる。Store APIのprices.priceも同時にvariable product
の基準(最小)価格を返すため、追加のバリアント解決ロジックは不要。
実データ確認済み(2026-09再確認、全55件中1件が該当): 「エチオピア　グジ
G-1　ウラガ　タベ・ブルカWS　ウォッシュド　100 or 200g」のみ「100g or
200g」ではなく「100 or 200g」と最初の数字にg/ｇが付かない表記揺れがあり、
WEIGHT_PATTERNの単純な最初マッチだと"200g"を誤って拾ってしまう。
WEIGHT_OR_PATTERNで「数字(g任意) or 数字g」の形を専用に検出し、2つの
数値の小さい方を採用するextract_weight_g()で対処する。

【非コーヒー豆商品の除外について】
実データ確認済み(全146件): 焼き菓子(ブルーノスナック各種)・器具
(ハリオ/ORIGAMI/KINTO/珈琲考具の温度計・ケトル・ドリッパー・
ペーパーフィルター・ビーカーサーバー・ラテボウル・フレンチプレス)・
LUONTOCOFFEEオリジナルクリアファイル・各種ドリップバッグ/ドリップ
パック・水出しコーヒー関連(バッグ・ラテベース)・定期便(月極サブスク
リプション)・お楽しみBOX(月替わり福袋)・KUTEのおやつ箱(焼き菓子福袋)・
ギフト各種(セット・詰め合わせ含む)・店主お任せ４種セット/初回おすすめ
セット(複数銘柄の詰め合わせで単一銘柄を特定できない)・ルオントレウナ
会員様限定特典(価格0円のプレゼント企画)・『あなたのためだけにお作りし
ます』カスタムオーダー(価格100000円のプレースホルダー)・配送オプション/
ギフトラッピングオプション(商品ではない付帯オプション)が非対象。
NON_BEAN_KEYWORDSで除外する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "LUONTOCOFFEE",
    "url": "https://luontocoffee.jp/",
    "platform": "WooCommerce",
    "address": "愛知県岡崎市大和町塗御堂40-1",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なWordPressのrobots.txt。"
                          "/wp-admin/のみDisallow、admin-ajax.phpは個別にAllow)",
}

API_URL = "https://luontocoffee.com/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ブルーノスナック", "おやつ箱", "お楽しみBOX", "ギフト", "ドリップバッグ", "ドリップパック",
    "Drip Bag", "水出し", "ラテベース", "定期便", "配送オプション", "ラッピング",
    "会員様限定", "あなたのためだけに", "初回おすすめセット", "店主お任せ", "詰め合わせ",
    "ハリオ", "ORIGAMI", "KINTO", "珈琲考具", "V60", "フレンチプレス", "ビーカーサーバー",
    "ドリッパー", "ペーパーフィルター", "ミルクピッチャー", "ケトル", "温度計", "ラテボウル",
    "クリアファイル",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 理由はモジュールdocstring参照(「100g or 200g」表記が基本だが、実データ
# 確認済み: 一部商品(エチオピア グジG-1等)は「100 or 200g」のように最初の
# 数字にg/ｇが付かない表記揺れがあり、WEIGHT_PATTERNの単純な最初マッチでは
# "200g"の方を誤って最小重量として拾ってしまう。"数字(g無し可) or 数字g"の
# 形を専用パターンで検出し、2つの数値の小さい方を採用する)
WEIGHT_OR_PATTERN = re.compile(r"(\d+)\s*(?:[gｇ])?\s*or\s*(\d+)\s*[gｇ]", re.IGNORECASE)


def extract_weight_g(name: str) -> int | None:
    or_m = WEIGHT_OR_PATTERN.search(name)
    if or_m:
        return min(int(or_m.group(1)), int(or_m.group(2)))
    weight_m = WEIGHT_PATTERN.search(name)
    return int(weight_m.group(1)) if weight_m else None


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def build_record(product: dict) -> dict | None:
    name = (product.get("name") or "").strip()
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(name)
    price = (product.get("prices") or {}).get("price")
    price = int(price) if price is not None else None
    product_url = product.get("permalink")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = not product.get("is_in_stock", True)
    stock_status = detect_stock_status(name, structural_out_of_stock)
    weight_g = extract_weight_g(name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_luontocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_luontocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
