# -*- coding: utf-8 -*-
"""
scrape_tokinokairou.py

名曲喫茶 時の回廊(https://www.tokinokairou.com/、岡山県倉敷市下津井田之浦1-16-22)の商品情報を取得する。BASE。

【店舗について】
名曲喫茶の店頭販売あり(営業10〜18時・水曜定休)。aboutに「最新鋭の焙煎機で、細かく丁寧に焙煎した煎りたて珈琲」(時の焙煎社)。
豆の主力は120g/¥1,000の各銘柄と、100g/¥980の「極深」シリーズ(5銘柄、120g版とは焙煎度が違う別商品として両方出力)。
同じ豆の別重量(Mozart 200g=時の回廊珈琲、Beethoven 200g=マンデリンG1と同スペック)は最小重量の商品のみ採用。
除外: ドリップバッグ・水出しパック・Brahms and Tchaikovsky(2種セット)・Mozart and Beethoven(各200gセット)・選べる6個セット・カップ/皿/ポストカード、インフューズド製法(パッションフルーツ)、カシャーサ樽熟成(送料込み価格の特殊品)。

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
    "name": "名曲喫茶 時の回廊",
    "url": "https://www.tokinokairou.com/",
    "platform": "BASE",
    "address": "岡山県倉敷市下津井田之浦1-16-22",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-11-02確認。User-agent: * は Allow: / で /cart/ 等のみ禁止。python-requests/curl等は個別にDisallow: /指定のため識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASE(独自ドメイン www.tokinokairou.com)のabout・特商法・サイトマップ・各商品ページを2026-11-02に確認。住所は特商法の「〒711-0925 岡山県倉敷市下津井田之浦1-16-22」、第三者サイト(gltjp.com)も同住所。ブログ最新は2020年だが商品は販売中表示",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://www.tokinokairou.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.2  # BASEは5秒以上

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動))
ITEMS = [
    ('128322057', 'ホンジュラス(120g)', 120, None, '中煎り', None),
    ('128012873', '珈琲『余韻』(120g)', 120, 'ブレンド', None, None),
    ('99392992', '時の回廊珈琲(120g)', 120, None, '中煎り', 'エチオピア'),
    ('99367046', '時の回廊珈琲 深煎り(120g)', 120, None, '深煎り', 'エチオピア'),
    ('99391538', 'コロンビア エルパライソ農園(120g)', 120, None, '中煎り', None),
    ('99366647', 'タンザニア キリマンジャロAA(120g)', 120, None, '中煎り', None),
    ('99366578', 'ブラジル(120g)', 120, None, '中煎り', None),
    ('99366518', 'ペルー オーガニック(120g)', 120, None, '中煎り', None),
    ('99366365', 'グァテマラSHB(120g)', 120, None, '中煎り', None),
    ('99366299', 'エチオピア レケンプティ(120g)', 120, None, '中煎り', None),
    ('99366221', 'コロンビア(120g)', 120, None, '中煎り', None),
    ('81033828', 'インドネシア ジャバ ロブ(120g)', 120, None, '中煎り', None),
    ('81032856', 'インドネシア マンデリンG1(120g)', 120, None, '深煎り', None),
    ('81032688', 'インドネシア オーガニック ガヨマウンテン(120g)', 120, None, '中煎り', None),
    ('81032407', 'グァテマラ オーガニック(120g)', 120, None, '中煎り', None),
    ('65061839', 'ブラジル フルッタメルカドン(120g)', 120, None, '中煎り', None),
    ('65570156', 'カフェインレス エチオピア(120g)', 120, None, '中煎り', None),
    ('90013053', 'カフェインレス コロンビア(120g)', 120, None, 'シティロースト', None),
    ('65569566', 'カフェインレス ブラジル(120g)', 120, None, '中煎り', None),
    ('115471376', '極深ペルー 100g', 100, None, '極深煎り', None),
    ('115472105', '極深ブラジル 100g', 100, None, '極深煎り', None),
    ('115472277', '極深コロンビア 100g', 100, None, '極深煎り', None),
    ('115472361', '極深エチオピア 100g', 100, None, '極深煎り', None),
    ('115472646', '極深グァテマラ 100g', 100, None, '極深煎り', None),
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
    with open("data_tokinokairou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokinokairou.json に出力しました")


if __name__ == "__main__":
    main()
