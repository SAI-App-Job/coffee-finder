# -*- coding: utf-8 -*-
"""
scrape_yokoshimacoffee.py

ヨコシマ珈琲焙煎所(https://roastery.yokoshimacoffee.jp/、京都府京都市西京区嵐山朝月町5-18)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-21): カテゴリ「コーヒー豆」(categories/1274340)の15商品のうち、「100g×2 きまぐれセット」「200gお買い得セット」の2つのセットを除く豆13銘柄(ブレンド3・シングル10)を収録。
ドリップパック・水出し・ギフト・グッズ・Tシャツは除外。商品ページに重量の記載はないが、ブログのオープン日メニュー「コーヒー豆(100g)」と
「100g×2 ヨコシマな焙煎士きまぐれセット(¥1,300)」の説明から1商品=100gと判断した(推定)。
商品名の「roast N」は焙煎度の目安(4=中煎り、5〜5.5=中深煎り、6〜6.5=深煎り、7=フレンチロースト入口)で、商品名の表記(中煎り/中深煎り/深煎り)に合わせた。
実店舗: 京都市西京区嵐山朝月町5-18の焙煎所(食べログ「ヨコシマ珈琲焙煎所」コーヒースタンド、ブログに焙煎所オープン日の告知あり)。ただし2024〜2025年のブログはマルシェ出店の告知が中心。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可、/cart/ 等のみ禁止)。本スクレイパーは識別可能な独自User-Agentを使用し、
リクエスト間隔は5秒以上とする。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {'name': 'ヨコシマ珈琲焙煎所',
 'url': 'https://roastery.yokoshimacoffee.jp/',
 'platform': 'BASE',
 'address': '京都府京都市西京区嵐山朝月町5-18',
 'prefecture': '京都府',
 'robots_txt_status': '実質許可(2026-10-21確認。User-agent: '
                      '*は許可で/cart/等のみ禁止、python-requests/curlは個別にDisallow。識別可能なUser-Agentを使用)',
 'source_note': 'BASE独自ドメイン(https://roastery.yokoshimacoffee.jp/)のカテゴリ「コーヒー豆」(categories/1274340)全15商品と各商品ページを2026-10-21に確認。住所は特商法ページ(/law)。ブログ(/blog)は2025-05-07が最新。【弱い点】常設店ではなく、焙煎所は不定期(日曜午後等)のオープンとマルシェ出店が中心(/aboutに「京都・滋賀のマルシェを中心に活動」)。商品ページに重量表記がなく、100gは出店時メニュー「コーヒー豆(100g)」と「100g×2セット」の説明から判断',
 'last_verified_at': '2026-10-21'}

BASE_URL = "https://roastery.yokoshimacoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 焙煎度の補足(roast_hint))
ITEMS = [
    ('128380994', 'ケニア ニエリ ガタイティファクトリー ウォッシュAA', 100, None, '深煎り', 'roast7(フレンチロースト入口まで)'),
    ('52461050', 'グアテマラ パストーレス ピーベリー', 100, None, '深煎り', 'roast 6.5'),
    ('68496728', 'ヨコシマブレンド ディープ', 100, 'ブレンド', '深煎り', 'roast 6.5'),
    ('16027382', 'グアテマラ エルインヘルト タンザニア区画', 100, None, '深煎り', 'roast 6'),
    ('16027529', 'エチオピア イルガチェフェ G1 コンガ農協 深煎り', 100, None, '深煎り', 'roast 6'),
    ('96879803', '団地ブレンド', 100, 'ブレンド', '中深煎り', 'roast 5.5'),
    ('74335825', 'ペルー アンデスブルー', 100, None, '中深煎り', 'roast 5.5'),
    ('128382595', 'ボリビア レアンドラ アングロ', 100, None, '中深煎り', 'roast 5'),
    ('24319255', 'エチオピア イルガチェフェ G2 デカフェ', 100, None, '中深煎り', 'roast 5'),
    ('55904614', 'ヨコシマブレンド ライト', 100, 'ブレンド', '中煎り', 'roast 4.5'),
    ('92704386', 'コスタリカ ジャガー アナエロビック ナチュラル', 100, None, '中煎り', 'roast 4'),
    ('32552517', 'エチオピア イルガチェフェ G1 コンガ農協 中煎り', 100, None, '中煎り', 'roast 4'),
    ('149533532', 'ウガンダ マウントエルゴン ブラックハニー', 100, None, '中浅煎り', 'roast 3.5'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None, roast_hint: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    full_desc = html_lib.unescape(desc_m.group(1)) if desc_m else None
    desc = re.sub(r"\s+", " ", full_desc).strip()[:400] if full_desc else None
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
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"
    if not parsed["processing_method"] and full_desc:
        parsed["processing_method"] = extract_from_description(full_desc.replace("生産処理：", "精選方法："))["processing_method"]

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
        "roast_hint": roast_hint,
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
    for item_id, name, weight_g, category_override, roast_level, roast_hint in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, roast_hint)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yokoshimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yokoshimacoffee.json に出力しました")


if __name__ == "__main__":
    main()
