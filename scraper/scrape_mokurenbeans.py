# -*- coding: utf-8 -*-
"""
scrape_mokurenbeans.py

珈琲豆 木蓮(https://mokurenbeans.thebase.in/、岡山県総社市三輪141-2)の商品情報を取得する。BASE。

【店舗について】
公式サイト(mokuren-coffee.com)に「少量自家焙煎」「実店舗では試飲もできます」、特商法に営業時間10時〜18時(定休 日・月・火・水)。
注意: 和歌山の「珈琲もくれん」(scrape_mokuren.py)とは別の店。
全商品が200g単位(about・特商法に「価格は200g単位」)で、100gの設定はない。そのため重量は200gで出力する。

【robots.txtについて】
2026-11-02確認: User-agent: * は Allow: / で、Disallow は /cart/ /web_cart/ /shops/ 等のみ。
python-requests/curl 等は個別に Disallow: / 指定のため、本スクレイパーは識別可能な
独自User-Agent(CoffeeFinderBot)を使用し、リクエスト間隔は5秒以上とする。

【対象商品の選定について】
実データ確認済み(2026-11-02): 下のITEMSは、サイトマップ/カテゴリ一覧の全商品から
豆(シングルオリジン・ブレンド・デカフェ)のみを選んだもの。ドリップバッグ・セット・
ギフト・雑貨・水出しパック等は除外。同一銘柄が重量違いで並ぶ場合は最小重量の商品を
代表にしている。商品名・重量・焙煎度は商品ページの表記を確認したうえでITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆 木蓮",
    "url": "https://mokurenbeans.thebase.in/",
    "platform": "BASE",
    "address": "岡山県総社市三輪141-2",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-11-02確認。User-agent: * は Allow: / で /cart/ 等のみ禁止。python-requests/curl等は個別にDisallow: /指定のため識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASEショップ(https://mokurenbeans.thebase.in/)のabout・特商法・サイトマップ・各商品ページと公式サイト(http://mokuren-coffee.com/)を2026-11-02に確認。住所は特商法・公式サイトの「総社市三輪141-2(〒719-1132)」",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://mokurenbeans.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.2  # BASEは5秒以上

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動))
ITEMS = [
    ('32194238', 'グアテマラ アンティグア アゾテア', 200, None, 'フルシティロースト', None),
    ('31819379', 'グアテマラ ウエウエティナンゴ カツーラ', 200, None, 'シティロースト', None),
    ('31819794', 'ブラジル ブルボン パルプドナチュラル', 200, None, 'シティロースト', None),
    ('31820553', 'コロンビア ウィラ スィートベリー', 200, None, 'フレンチロースト', None),
    ('81380486', 'ルワンダ フムレ ブルボン', 200, None, '中深煎り', None),
    ('53546949', 'コスタリカ ブラックハニー', 200, None, None, None),
    ('31820850', 'エチオピア イルガチェフェ ナチュラル', 200, None, 'シティロースト', None),
    ('81380572', 'ブルンジ ギヘレ ナチュラル', 200, None, 'ハイロースト', None),
    ('31843740', 'エチオピア イルガチェフェ ウオッシュド (モカ)', 200, None, 'ハイロースト', None),
    ('42508262', 'タンザニア ジェニュイン キリマンジャロ AA (キリマンジャロ)', 200, None, 'ハイロースト', None),
    ('42507628', 'ケニア マサイAA 深煎り', 200, None, '深煎り', None),
    ('31826750', 'インドネシア マンデリン ビンタンリマ', 200, None, 'フレンチロースト', None),
    ('31827377', 'みわブレンド', 200, 'ブレンド', None, None),
    ('42508209', 'みのりブレンド', 200, 'ブレンド', '中深煎り', None),
    ('32356072', '木蓮 ブレンド', 200, 'ブレンド', '深煎り', None),
    ('31827155', '深煎り ブレンド', 200, 'ブレンド', 'フレンチロースト', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level, origin_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[warn] 取得失敗(回避せずスキップ): item_id={item_id} status={resp.status_code}")
        return None
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # unpurchasable=全バリエーション購入不可(品切れ)。partially_purchasable=一部のみ不可なので販売中扱い
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
        if origin_override:
            parsed["origin_country"] = origin_override
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


def scrape_all_products():
    records = []
    for i, (item_id, name, weight_g, category_override, roast_level, origin_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mokurenbeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mokurenbeans.json に出力しました")


if __name__ == "__main__":
    main()
