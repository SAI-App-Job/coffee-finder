# -*- coding: utf-8 -*-
"""
scrape_bluedoorcoffee.py

BlueDOOR Coffee(https://bluedoor.base.shop/、神奈川県横浜市青葉区寺家町360)の商品情報を取得する。BASE(https://bluedoor.base.shop)。

【店舗発見の経緯】
神奈川県の新規発掘調査(2026-10-21)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 100g単位(豆)の焙煎豆を対象とし、同一銘柄で焙煎度(High/City/Fullcity Roast)ごとに別商品のものはそれぞれ収録。ドリップバッグ・水出し(COLD BREW)・ギフト・キャニスターは除外。
商品名・重量・産地・分類は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格(割引表示がある場合は割引後の販売価格)・在庫(item_purchasability)・説明(og:description)・
焙煎度(ページ内の「■ロースト」等の表記。ITEMSで明示した場合はそちらを優先)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BlueDOOR Coffee",
    "url": "https://bluedoor.base.shop/",
    "platform": "BASE",
    "address": "神奈川県横浜市青葉区寺家町360",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://bluedoor.base.shop/law (事業者所在地・営業時間10:00〜18:00)、/about (富士珈機5kg釜・井上製作所1kg釜で自家焙煎)、Walkerplus記事(寺家ふるさと村周辺の1号店で焙煎、たまプラーザ2号店)、各商品ページを2026-10-20に確認。たまプラーザ店は別店舗(焙煎は寺家町)。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://bluedoor.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneならページから判定), 産地(ブレンドはNone))
ITEMS = [   ('24837151', '里山ブレンド High Roast', 100, 'ブレンド', 'ハイロースト', None),
    ('24837229', '田園ブレンド High Roast', 100, 'ブレンド', 'ハイロースト', None),
    ('24837032', '緑風ブレンド City Roast', 100, 'ブレンド', 'シティロースト', None),
    ('24836500', '天空ブレンド Fullcity Roast', 100, 'ブレンド', 'フルシティロースト', None),
    ('24836546', '大地ブレンド Fullcity Roast', 100, 'ブレンド', 'フルシティロースト', None),
    ('33401777', 'AUTUMN BLEND(秋ブレンド) City Roast / Fullcity Roast', 100, 'ブレンド', None, None),
    ('29023069', 'COLOMBIA High Roast', 100, None, 'ハイロースト', 'コロンビア'),
    ('29024590', 'COLOMBIA City Roast', 100, None, 'シティロースト', 'コロンビア'),
    ('29022302', 'COLOMBIA Fullcity Roast', 100, None, 'フルシティロースト', 'コロンビア'),
    ('29022833', 'ETHIOPIA High Roast', 100, None, 'ハイロースト', 'エチオピア'),
    ('29024036', 'ETHIOPIA City Roast', 100, None, 'シティロースト', 'エチオピア'),
    ('29022430', 'ETHIOPIA Fullcity Roast', 100, None, 'フルシティロースト', 'エチオピア'),
    ('29001545', 'BRASIL High Roast', 100, None, 'ハイロースト', 'ブラジル'),
    ('29024445', 'BRASIL City Roast', 100, None, 'シティロースト', 'ブラジル'),
    ('24837352', 'BRASIL Fullcity Roast', 100, None, 'フルシティロースト', 'ブラジル'),
    ('29022960', 'GUATEMALA High Roast', 100, None, 'ハイロースト', 'グアテマラ'),
    ('29021851', 'GUATEMALA Fullcity Roast', 100, None, 'フルシティロースト', 'グアテマラ'),
    ('29021699', 'INDONESIA Fullcity Roast', 100, None, 'フルシティロースト', 'インドネシア'),
    ('29024216', 'TANZANIA City Roast', 100, None, 'シティロースト', 'タンザニア')]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
DISCOUNT_PATTERN = re.compile(r"¥\s*([\d,]+)\s*\d+%\s*OFF\s*¥\s*([\d,]+)")
ROAST_PATTERNS = [
    re.compile(r"■\s*ロースト\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)"),
    re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)に(?:仕上げ|焙煎)"),
]


def page_text(html_text: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t))


def build_record(item_id: str, name: str, weight_g: int, category_override, roast_override, origin) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        print(f"[warn] HTTP {resp.status_code}: item_id={item_id}")
        return None
    html_text = resp.text
    text = page_text(html_text)

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    disc_m = DISCOUNT_PATTERN.search(text)
    if disc_m:  # 割引表示(例: ¥1,200 10%OFF ¥1,080)がある場合は割引後の販売価格
        price = int(disc_m.group(2).replace(",", ""))
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    roast = roast_override
    if not roast:
        for pat in ROAST_PATTERNS:
            m = pat.search(text)
            if m:
                roast = m.group(1)
                break

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
        if origin:
            parsed["origin_country"] = origin
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL_SEC)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bluedoorcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bluedoorcoffee.json に出力しました")


if __name__ == "__main__":
    main()
