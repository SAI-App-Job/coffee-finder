# -*- coding: utf-8 -*-
"""
scrape_suuscoffee.py

喫茶スーズ焙煎所(https://suus.theshop.jp/、愛知県名古屋市南区桜台1-22-5)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛知県)の新規発掘で発見。住所は/law(特定商取引法に基づく表記)で確認済み。

【対象商品について】
実データ確認済み(2026-10時点): 全12商品(すべて豆)。商品説明に「200g」と明記されているものは200g。アイスコーヒー用デカフェのみ重量の記載が無くnull。焙煎度は商品説明の記述から採用(未記載のものはnull)。パプアニューギニアの「ハイランド」を焙煎度と誤判定しないよう焙煎度を明示した。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description、無い場合は商品説明欄)は商品ページから取得する。
在庫は item_purchasability が unpurchasable の場合のみ品切れとし、一部バリエーションのみ
在庫切れ(partially_purchasable)の場合は販売中として扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "喫茶スーズ焙煎所",
    "url": "https://suus.theshop.jp/",
    "platform": "BASE",
    "address": "愛知県名古屋市南区桜台1-22-5",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://suus.theshop.jp"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('12690893', 'スペシャルティSUUSブレンド', 200, None, None),
    ('28374336', 'ブラジル ブルボン クラシコ カンタトゥーバ農園', 200, None, '中深煎り'),
    ('28374216', 'パプア ニューギニア ハイランドスウィート キガバー農園 AX', 200, None, '中煎り'),
    ('12722490', '有機栽培 ペルー アルパカ', 200, None, '中深煎り'),
    ('12722805', 'カフェインレスコーヒー豆 デカフェ', 200, None, '中深煎り'),
    ('13097419', 'スペシャリティ アイスコーヒーブレンド', 200, None, '深煎り'),
    ('13098578', 'アイスコーヒー用 カフェインレスコーヒー豆 デカフェ(ブラジル)', None, None, '深煎り'),
    ('13098869', 'ブラジル サントアントニオ プレミアム ショコラ ピーベリー', 200, None, '中深煎り'),
    ('13141694', 'コロンビア スウィートベリーSUP', 200, None, None),
    ('13141780', 'マンデリン ミトラ G1', 200, None, '深煎り'),
    ('13141864', 'グアテマラ アンティグア アゾテア農園ブルボン', 200, None, '中深煎り'),
    ('28374918', 'エチオピア イルガチャフィー ベレカ G1', 200, None, '中煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {'28374216': 'パプアニューギニア'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
DESC_FALLBACK_PATTERN = re.compile(r'<div class="itemDescription">(.*?)</div>', re.S)
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PRICE_FALLBACK_PATTERN = re.compile(r"'itemPrice':\s*(\d+)")
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def extract_description(html_text: str) -> str | None:
    m = DESC_PATTERN.search(html_text)
    if m:
        text = html_lib.unescape(m.group(1))
    else:
        m = DESC_FALLBACK_PATTERN.search(html_text)
        if not m:
            return None
        text = html_lib.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    text = re.sub(r"\s+", " ", text).strip()[:400]
    return text or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc = extract_description(html_text)
    price_m = PRICE_PATTERN.search(html_text) or PRICE_FALLBACK_PATTERN.search(html_text)
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
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_suuscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_suuscoffee.json に出力しました")


if __name__ == "__main__":
    main()
