# -*- coding: utf-8 -*-
"""
scrape_oinaicoffee.py

oinai coffee(https://oinaicoffee.thebase.in/、京都府長岡京市長岡3丁目7-17)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-21): 全8商品のうち、100gの豆5銘柄(ブレンド1・シングル4、デカフェ含む)を収録。
OINAIブレンド500g(65530848)は同銘柄の大容量のため最小重量の100gを代表とし除外。ドリップバッグ(単品・5個入)は除外。
豆の状態での発送、粉は注文時に申告(価格同一)。ブレンドは「中煎の豆をベース」との記載から中煎り。
実店舗: 長岡京市長岡3-7-17の店舗(公式サイトに営業案内 12:30〜18:00・日水定休、駐車場案内)。「ご注文をいただいてから焙煎」(公式トップ)。

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

SHOP_INFO = {'name': 'oinai coffee',
 'url': 'https://oinaicoffee.thebase.in/',
 'platform': 'BASE',
 'address': '京都府長岡京市長岡3丁目7-17',
 'prefecture': '京都府',
 'robots_txt_status': '実質許可(2026-10-21確認。User-agent: '
                      '*は許可で/cart/等のみ禁止、python-requests/curlは個別にDisallow。識別可能なUser-Agentを使用)',
 'source_note': 'BASE(https://oinaicoffee.thebase.in/)のトップ(全8商品)・各商品ページ・/law、公式サイト(https://oinai-coffee.com/)を2026-10-21に確認。公式サイトのお知らせ最新は2026-09-30。【注意】公式サイトの店頭価格(OINAIブレンド100g税込600円、シングル700円〜)は2026-09-21の価格改定後で、BASEの掲載価格(700円/800円等)と差がある',
 'last_verified_at': '2026-10-21'}

BASE_URL = "https://oinaicoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 焙煎度の補足(roast_hint))
ITEMS = [
    ('32972690', 'OINAIブレンド', 100, 'ブレンド', '中煎り', '中煎の豆をベース'),
    ('36005536', 'エチオピア 浅煎り', 100, None, '浅煎り', None),
    ('39491122', 'ブラジル 中煎り', 100, None, '中煎り', None),
    ('36005593', 'グアテマラ 深煎り', 100, None, '深煎り', None),
    ('39491087', 'メキシコ デカフェ 深煎り', 100, None, '深煎り', None),
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
    with open("data_oinaicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oinaicoffee.json に出力しました")


if __name__ == "__main__":
    main()
