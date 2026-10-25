# -*- coding: utf-8 -*-
"""
scrape_doorscoffeeroastery.py

DOORS COFFEE ROASTERY(https://shop.doorscoffee.jp/、京都府相楽郡笠置町笠置平田26)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-21): カテゴリ「Coffee」27商品のうち、焙煎豆の通常版(ポスト投函・200g)7銘柄(ブレンド1・シングル6)と期間限定の彩葉(200g)の計8銘柄を収録。
同銘柄の【ギフトコーヒー】版(ギフト)・【生豆】・飲み比べセット(30g/50g/100g)・コールドブリュー/ミルクブリューパック・コーヒーバッグ・ディップスタイルセットは除外。
全商品200g単位の販売(最小重量)。「ご注文後に自家焙煎」(各商品説明)で、豆のまま/挽き豆の選択式(豆のままを採用)。
「森音 -MORINONE-」は商品名が「オリジナルブレンド」だが、説明がインドネシア産リントン・マンデリン単一のため、ストレート(インドネシア)として扱った。
焙煎度は商品説明の表記(ハイロースト=中浅煎り、シティロースト=中深煎り、フルシティ/フレンチロースト=深煎り)に従った。
実店舗: 京都府相楽郡笠置町のロースタリー・コーヒースタンド(公式サイト。火水定休)。

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

SHOP_INFO = {'name': 'DOORS COFFEE ROASTERY',
 'url': 'https://shop.doorscoffee.jp/',
 'platform': 'BASE',
 'address': '京都府相楽郡笠置町笠置平田26',
 'prefecture': '京都府',
 'robots_txt_status': '実質許可(2026-10-21確認。User-agent: '
                      '*は許可で/cart/等のみ禁止、python-requests/curlは個別にDisallow。識別可能なUser-Agentを使用)',
 'source_note': 'BASE独自ドメイン(https://shop.doorscoffee.jp/)のカテゴリ「Coffee」(categories/5189898、27商品)・各商品ページ、公式サイト(https://doorscoffee.jp/)を2026-10-21に確認。住所は特商法ページ(/law)と公式サイト。お知らせ最新は2026-09-22。「彩葉」は期間限定(10月末まで)',
 'last_verified_at': '2026-10-21'}

BASE_URL = "https://shop.doorscoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 焙煎度の補足(roast_hint))
ITEMS = [
    ('85297030', '扉 -TOBIRA- オリジナルブレンド', 200, 'ブレンド', '中深煎り', 'シティロースト'),
    ('85296732', '暁 -AKATSUKI- グアテマラ', 200, None, '中深煎り', 'シティロースト'),
    ('85296831', '清風 -SEIFU- エチオピア イルガチェフェ', 200, None, '中深煎り', 'シティロースト'),
    ('85296881', '稜線 -RYOSEN- コロンビア ピンクブルボン アナエロビック', 200, None, '深煎り', 'フルシティ'),
    ('85296914', '黄昏 -TASOGARE- ケニア', 200, None, '中浅煎り', 'ハイロースト'),
    ('85296985', '月夜 -TSUKIYO- コロンビア デカフェ', 200, None, '中浅煎り', 'ハイロースト'),
    ('150414675', '森音 -MORINONE- インドネシア マンデリン', 200, None, '深煎り', 'フレンチロースト'),
    ('157405948', '彩葉 -IROHA- 東ティモール(期間限定)', 200, None, '中浅煎り', 'ハイロースト'),
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
    with open("data_doorscoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_doorscoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
