# -*- coding: utf-8 -*-
"""
scrape_bijouxcoffeechuo.py

Bijoux Coffee CHUO(ビジュコーヒー、https://bijouxcoffee.base.shop/)の商品情報を取得する。BASE。

【住所について】
店舗自身の特定商取引法ページ(/law)の記載は「〒409-3803 山梨県中央市若宮44-7 ピュアリーフガーデン5号」
(営業時間10:30-18:30)。第三者情報では昭和町押越2429-3(Bijoux Coffee本店)とされるが、
CHUO店名と一致する/lawの住所を採用した(2026-10-12確認)。

【店舗発見の経緯】
全国再調査(山梨県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-12時点): 全19商品のうち、リキッドコーヒー2件(1L)を除く
自家焙煎豆17銘柄(すべて200g)を対象とする。ローストカカオ豆は商品として存在しない。
焙煎度は商品名の「○○ロースト」表記から転記した。
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
    "name": "Bijoux Coffee CHUO",
    "url": "https://bijouxcoffee.base.shop/",
    "platform": "BASE",
    "address": "山梨県中央市若宮44-7 ピュアリーフガーデン5号",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://bijouxcoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('160418450', 'ペルー 【カハマルカ エルメル・ネイラ農園】カトゥーラ シティロースト', 200, None, 'シティロースト'),
    ('160414314', 'コスタリカ【ロス・クレストネス】エル・セロ フレンチロースト', 200, None, 'フレンチロースト'),
    ('157952009', 'グアテマラ「サンタカタリーナ農園」ピーベリー フレンチロースト', 200, None, 'フレンチロースト'),
    ('157951510', 'グアテマラ「サンタカタリーナ農園」ピーベリー シティロースト', 200, None, 'シティロースト'),
    ('128467248', 'タンザニア ブラックバーン農園 シティロースト', 200, None, 'シティロースト'),
    ('132807696', 'エチオピア 【グジ】ゴロ・ベデッサD.S. ウォッシュト シティロースト', 200, None, 'シティロースト'),
    ('120079828', 'ペルー 【フェスパ農園 ウィルダー・ガルシア】ブルボン フレンチロースト', 200, None, 'フレンチロースト'),
    ('51213558', 'インドネシア スマトラ オナンガンジャン・マンデリン フレンチロースト', 200, None, 'フレンチロースト'),
    ('108031851', 'DECAF カフェインレスコーヒー メキシコ【トリウンフォ・ベルデ】 シティロースト', 200, None, 'シティロースト'),
    ('51214446', 'マイルドブレンド シティロースト', 200, 'ブレンド', 'シティロースト'),
    ('51214490', '山の都ブレンド シティロースト', 200, 'ブレンド', 'シティロースト'),
    ('51214528', 'ショコラブレンド フルシティロースト', 200, 'ブレンド', 'フルシティロースト'),
    ('51214572', '深いりブレンド フレンチロースト', 200, 'ブレンド', 'フレンチロースト'),
    ('93018502', 'AUTUMN BLEND【秋彩 AKI IRO】 フルシティロースト', 200, 'ブレンド', 'フルシティロースト'),
    ('104441053', 'エチオピア イルガチェフェ【ウォテ2300】ナチュラル シティロースト', 200, None, 'シティロースト'),
    ('88056713', 'ケニア 【ギチャサイニ ファクトリー】 フレンチロースト', 200, None, 'フレンチロースト'),
    ('51213226', 'ブラジル「マカウバデシーマ農園」ボイアナチュラル フレンチロースト', 200, None, 'フレンチロースト'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
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
    with open("data_bijouxcoffeechuo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bijouxcoffeechuo.json に出力しました")


if __name__ == "__main__":
    main()
