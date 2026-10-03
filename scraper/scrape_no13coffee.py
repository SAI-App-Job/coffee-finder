# -*- coding: utf-8 -*-
"""
scrape_no13coffee.py

SPECIALTY COFFEE BEANS No.13(https://no13.base.shop/、神奈川県横須賀市佐野町5-12-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
神奈川県の自家焙煎店調査(Kanagawa A)で発見。特定商取引法表記・ABOUTページで神奈川県横須賀市の所在地(実店舗1店舗、カフェ併設)を確認した。公式サイト上に「自家焙煎」の明記はなく、自家焙煎である点は外部記事(Knot Magazine)の記述による。

【対象商品について】
実データ確認済み(2026-10時点): 全20商品のうちドリップバッグ・水出しパック・飲み比べセット・定期便を除いた焙煎豆13銘柄(ストレート11・ブレンド2)。商品タイトル先頭の内容量(30g/60g/100g。希少ロットは少量)を重量とし、各銘柄1ページのみのためそのまま代表とした。焙煎度は商品ページの「ロースト」欄。「季節のエスプレッソロースト」は産地の記載がないためブレンド扱い(産地None)。
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
    "name": "SPECIALTY COFFEE BEANS No.13",
    "url": "https://no13.base.shop/",
    "platform": "BASE",
    "address": "神奈川県横須賀市佐野町5-12-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://no13.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)(商品ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('154860829', 'ルワンダ フムレウォッシングステーション ブルボン ウォッシュド', 100, None, '浅煎り'),
    ('154673798', 'ベトナム ラン農園 イエローカトゥアイハニー', 100, None, '浅煎り'),
    ('153615158', '鎌倉ブレンド', 100, 'ブレンド', '中深煎り'),
    ('143778767', '台湾 Niuchoujiao農園 ゲイシャ ハニー', 30, None, '浅煎り'),
    ('143778565', 'パナマ ベルナルディーナ農園 ゲイシャナチュラル', 30, None, '浅煎り'),
    ('145461528', 'ボリビア タイピプラヤ アナエロビックウォッシュド', 60, None, '浅煎り'),
    ('140221000', 'ベトナム ティン農園 アナエロビックナチュラル', 100, None, '浅煎り'),
    ('132363533', 'インド パールマウンテン カルチャーナチュラル', 60, None, '浅煎り'),
    ('119029097', 'コロンビア エルパライソ YN-09 ライチピーチ', 60, None, '浅煎り'),
    ('99621702', 'タンザニア イエンガ農園 ウォッシュド', 100, None, '浅煎り'),
    ('59195741', 'カフェインレス メキシコ', 100, None, '浅煎り'),
    ('59189325', 'インドネシア マラバー農園 ウォッシュド', 100, None, '浅煎り'),
    ('141946595', '季節のエスプレッソロースト', 100, 'ブレンド', '中深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する(商品ID: 産地)
ORIGIN_OVERRIDES = {'143778767': '台湾'}

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
    with open("data_no13coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_no13coffee.json に出力しました")


if __name__ == "__main__":
    main()
