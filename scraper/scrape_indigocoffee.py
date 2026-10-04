# -*- coding: utf-8 -*-
"""
scrape_indigocoffee.py

Indigo Coffee Roasters(https://indigocoffee.theshop.jp/、大阪府枚方市岡東町19-20 エル枚方1F)の商品情報を取得する。THE SHOP(BASE系)。

【店舗発見の経緯】
全国再調査(大阪府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全28商品のうち定期便・Dip Style Coffee(ドリップバッグ類)・詰め合わせギフト・生豆選別サービスを除き、100g/200g/400gが別ページのため100gを代表とした5商品(シングル4・ブレンド1)。焙煎度は説明文の「焙煎度:」欄の括弧内から取得。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名がキャッチコピー付き・重量違いの重複登録などで、そのままでは使いにくいため)。
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
    "name": "Indigo Coffee Roasters",
    "url": "https://indigocoffee.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "大阪府枚方市岡東町19-20 エル枚方1F",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://indigocoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名・説明文から判定))
ITEMS = [
    ('147116995', 'La Villa Geisha Anaerobic Fermentation - Colombia(ラ・ビジャ ゲイシャ アナエロビック ファーメンテーション)', 100, None, None),
    ('154957458', 'Sidamo G-1 Bona Zuria Sedaka Natural - Ethiopia(シダモG-1 ボナ・ズリア セダカ ナチュラル)', 100, None, None),
    ('150413698', 'Mandheling Tobako - Indonesia(マンデリン トバコ)', 100, None, None),
    ('146376397', 'El Diamante Bourbon Natural - Honduras(エル・ディアマンテ ブルボン ナチュラル)', 100, None, None),
    ('73713923', 'House Blend No.1 "KOHAKU"', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

# 説明文(og:description)に混じる配送案内などの定型文の手前で打ち切るパターン
DESC_CUT_PATTERN = r"※ご使用前に"
# 商品名に焙煎度が無い場合に説明文から焙煎度を拾うパターン(最初のグループを採用)
DESC_ROAST_PATTERN = r"焙煎度[:：]\s*[^()（）]*[（(]([^）)]+)[）)]"

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_desc(raw: str) -> str | None:
    import html
    text = html.unescape(raw)
    if DESC_CUT_PATTERN:
        m = re.search(DESC_CUT_PATTERN, text)
        if m:
            text = text[:m.start()]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400] or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = clean_desc(desc_m.group(1)) if desc_m else None
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
        parsed["grade"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    roast = roast_level or parsed["roast_level"]
    if not roast and desc and DESC_ROAST_PATTERN:
        rm = re.search(DESC_ROAST_PATTERN, desc)
        if rm:
            roast = rm.group(1).strip()

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
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
    with open("data_indigocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_indigocoffee.json に出力しました")


if __name__ == "__main__":
    main()
