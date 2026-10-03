# -*- coding: utf-8 -*-
"""
scrape_coffeejade.py

Coffee Jade(https://coffeejade.thebase.in/、神奈川県厚木市)の商品情報を取得する。BASE。

【店舗発見の経緯】
神奈川県の自家焙煎店調査(Kanagawa A)で発見。特定商取引法表記はBASE社の所在地のみ。ショップのmeta説明(「コーヒージェイドは厚木市で自家焙煎をしています」)とABOUTページ(小さな焙煎所、自家焙煎珈琲店)から厚木市の自家焙煎店と判断し、所在地は市単位とした(番地「山際950-13」は外部情報のみで公式サイトでは未確認)。

【対象商品について】
実データ確認済み(2026-10時点): 全22商品のうちセット・ギフトバッグ・保存袋(ecotact)・珈琲缶・手ぬぐいを除いた焙煎豆10銘柄(ストレート6・ブレンド4)。全て200gで販売。10周年ブレンドの翡翠(中煎り)・琥珀(深煎り)・真夏の果実(中煎りブレンド)は焙煎度の記載あり。単一産地の銘柄は中煎り/深煎り(マンデリン・山のブレンドは深煎り/極深煎り)を購入時に選択する方式のため焙煎度None。商品名は「｜」以降のキャッチコピーと重量表記を除いた。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量表記付きのため)。
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
    "name": "Coffee Jade",
    "url": "https://coffeejade.thebase.in/",
    "platform": "BASE",
    "address": "神奈川県厚木市",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeejade.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)(商品ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('153469868', '翡翠', 200, 'ブレンド', '中煎り'),
    ('153474219', '琥珀', 200, 'ブレンド', '深煎り'),
    ('148445834', 'グァテマラ アンティグア イエローブルボン', 200, None, None),
    ('127231334', 'コロンビア ラス・ペルリタス', 200, None, None),
    ('102870616', 'エチオピア グジ ベンチネンカ G1', 200, None, None),
    ('68303714', 'エチオピア イルガチェフェ G1 コンガ農協 ナチュラル', 200, None, None),
    ('112229210', 'ブラジル チョコラータ', 200, None, None),
    ('112230142', 'インドネシア マンデリン ビンタンリマ', 200, None, None),
    ('112231000', '真夏の果実', 200, 'ブレンド', '中煎り'),
    ('34162894', '山のブレンド', 200, 'ブレンド', None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する(商品ID: 産地)
ORIGIN_OVERRIDES = {}

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
    with open("data_coffeejade.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeejade.json に出力しました")


if __name__ == "__main__":
    main()
