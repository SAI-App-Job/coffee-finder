# -*- coding: utf-8 -*-
"""
scrape_bonuscoffee.py

BONUS COFFEE Roastery(https://bonuscoffee.base.shop/、千葉県習志野市津田沼7-5-16)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。公式サイトの特定商取引法表記で千葉県内の所在地・自家焙煎を確認した。

【対象商品について】
実データ確認済み(2026-10時点): 習志野市の少量・注文後焙煎の自家焙煎所(公式表記は「BONUS COFFEE 焙煎所」、店舗は1店舗)。全11商品のうちギフトラッピングを除き、100g/200gが別ページのため100gを代表として収録した4銘柄。注文後焙煎でショップ側が焙煎度を決める(説明文に中煎り〜中深煎り想定等の記載のみ)ため焙煎度はNone。在庫がpartially_purchasableの商品は販売中として扱う。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(重量違いの重複登録や商品名の表記ゆれがあるため)。
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
    "name": "BONUS COFFEE Roastery",
    "url": "https://bonuscoffee.base.shop/",
    "platform": "BASE",
    "address": "千葉県習志野市津田沼7-5-16",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://bonuscoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('88435533', 'ケニア マサイ AA TOPGRADE ウォッシュド', 100, None, None),
    ('138217064', 'ベトナム クホ ファインロブスタ ハニー', 100, None, None),
    ('123448994', 'ベトナム クホ ファインロブスタ アナエロビックナチュラル', 100, None, None),
    ('154662945', 'インドネシア イワンさんのガヨ・マンデリン スマトラ式', 100, None, None),
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
    with open("data_bonuscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bonuscoffee.json に出力しました")


if __name__ == "__main__":
    main()
