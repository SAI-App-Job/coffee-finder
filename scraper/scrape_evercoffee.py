# -*- coding: utf-8 -*-
"""
scrape_evercoffee.py

ever coffee(https://evercoffee.base.shop/、京都府京都市右京区宇多野福王子町45-2)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全29商品のうち豆11銘柄。同一銘柄が100g/200gの別ページで並ぶため100gを代表とした。ドリップバッグ・定期便・選べる3袋セットを除いた。焙煎度は商品ページの【焙煎度】欄から取得。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
og:descriptionの先頭は全商品共通の店舗紹介文のため、「ちょっと贅沢をしてみませんか。」までを除いて採用する。

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
    "name": "ever coffee",
    "url": "https://evercoffee.base.shop/",
    "platform": "BASE",
    "address": "京都府京都市右京区宇多野福王子町45-2",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://evercoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('158697406', 'デイリーブレンド', 100, 'ブレンド', '中煎り'),
    ('158697081', '深煎りブレンド', 100, 'ブレンド', '深煎り'),
    ('158697008', 'ブラジル モンテアレグレ ナチュラル No.2', 100, None, '中深煎り'),
    ('158696555', 'ラオス サーン ウォッシュ Sc14UP', 100, None, '中煎り'),
    ('158695802', 'カメルーン ンベサ ピーベリー ウォッシュ G1', 100, None, '中煎り'),
    ('158695679', 'タイ ドイパンコン トンナム インスリットさん ケニアスタイル ウォッシュ', 100, None, '中煎り'),
    ('158695202', 'コロンビア ウィラ ラス モラス アナエロビックウォッシュ エクセルソ EP', 100, None, '中煎り'),
    ('158695081', 'コスタリカ パタリージョ農園 ウォッシュ SHB EP', 100, None, '中煎り'),
    ('158694946', 'エチオピア イルガチェフェ ゲデブ ラレサ ウォッシュ G2プレミアム', 100, None, '中深煎り'),
    ('158694702', 'カフェインレス メキシコ チアパス フィンカ ドンラファ ウォッシュ SHG', 100, None, '中煎り'),
    ('158694295', 'ルワンダ ウーマンコーヒー TUK農協 フリーウォッシュ A', 100, None, '中煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'158695679': 'タイ', '158696555': 'ラオス', '158695802': 'カメルーン'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip() if desc_m else None
    if desc:
        # 全商品共通の店舗紹介文(「ちょっと贅沢をしてみませんか。」まで)を除く
        desc = re.sub(r"^.*?ちょっと贅沢をしてみませんか。", "", desc).strip()
        # 【焙煎度】欄の「Medium Roast(中煎り)」以降に風味の説明がある商品は、その部分を採用する
        m_flavor = re.search(r"Roast（[^）]*）\s*(.+)$", desc)
        if m_flavor:
            desc = m_flavor.group(1).strip()
        desc = desc[:400] or None
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
    with open("data_evercoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_evercoffee.json に出力しました")


if __name__ == "__main__":
    main()
