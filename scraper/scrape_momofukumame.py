# -*- coding: utf-8 -*-
"""
scrape_momofukumame.py

百福豆珈琲(https://momofukumame.theshop.jp/、埼玉県坂戸市八幡1-3-42)の商品情報を取得する。BASE(THE SHOP)。

【対象商品について】
実データ確認済み(2026-10-26時点): sitemap.xmlの商品ページ(36件)から、焙煎豆17商品のみをITEMSに明示している。
ほとんどが200g売りの単一商品(重量違いの別ページは無い)のため、その銘柄の最小重量=200gを採用。
ジャマイカ・ブルーマウンテンNo.1のみ100g単位。
ドリップバッグ、定期便、セット、ギフトボックス、ショートブレッド等の菓子、手ぬぐい、マスキングテープは除外。
焙煎度は商品名の表記から取得。「中煎・深煎」「中深煎り/中煎り」など選択式の商品と、記載の無い商品は null。
価格・在庫・説明は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5.5秒。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, detect_processing_method

SHOP_INFO = {   'name': '百福豆珈琲',
    'url': 'https://momofukumame.theshop.jp/',
    'platform': 'BASE',
    'address': '埼玉県坂戸市八幡1-3-42',
    'prefecture': '埼玉県',
    'robots_txt_status': '実質許可(他のBASE系店舗と同一の記述。python-requests/curl等は個別にDisallow、User-agent: '
                         '*では許可。識別可能なUser-Agentを使用し、取得間隔は5.5秒)',
    'source_note': 'THE '
                   'SHOP(BASE系、https://momofukumame.theshop.jp/)のsitemap.xmlと各商品ページ、特商法(/law、〒350-0223 '
                   '埼玉県坂戸市八幡1-3-42、営業時間11:00~18:00・定休日月/金)を2026-10-26に確認。店頭販売の自家焙煎である旨は/aboutに記載。2026年の定期便商品あり(更新は新しい)',
    'last_verified_at': '2026-10-26'}

BASE_URL = "https://momofukumame.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5  # BASE系は5秒以上

# 商品ID, 表示名, 重量(g/不明はNone), カテゴリ(None=自動/"ブレンド"), 原産国(ブレンドはNone), 焙煎度(選択式・不明はNone), 精製方法の上書き(Noneなら説明文から検出)
ITEMS = [
    ('131982591', 'エチオピア ゲイシャ ケビルゲイシャ農園 G1 ナチュラル', 200, None, 'エチオピア', '浅煎り', None),
    ('131978474', 'インドネシア マンデリン アチェ ジャンボガヨ S19', 200, None, 'インドネシア', '深煎り', None),
    ('131982262', 'グアテマラ SHB ラス・ブリサス農園', 200, None, 'グアテマラ', '中深煎り', None),
    ('131980891', 'ブラジル カラメリッチ S18', 200, None, 'ブラジル', None, None),
    ('81607346', 'ジャマイカ ブルーマウンテンNo.1 クライスデール', 100, None, 'ジャマイカ', '中煎り', None),
    ('38866524', '百福豆ブレンド', 200, 'ブレンド', None, None, None),
    ('46044882', '時雨ブレンド', 200, 'ブレンド', None, '深煎り', None),
    ('74585733', '福雨ブレンド', 200, 'ブレンド', None, '中深煎り', None),
    ('44192655', '喜雨ブレンド(Q-BLEND)', 200, 'ブレンド', None, '中深煎り', None),
    ('50802362', 'ケニア マサイ AA', 200, None, 'ケニア', '深煎り', None),
    ('120747830', 'タンザニア キリマンジャロ イユラWS キボーAA', 200, None, 'タンザニア', '中深煎り', None),
    ('50807200', 'エチオピア イルガチェフィー ブナブナ G1 ナチュラル', 200, None, 'エチオピア', None, None),
    ('74583887', 'インドネシア トラジャ ランテカルア', 200, None, 'インドネシア', '中深煎り', None),
    ('97618858', 'エルサルバドル サンタリタ ブルボン', 200, None, 'エルサルバドル', '中深煎り', None),
    ('38079894', 'パプアニューギニア シグリ AA', 200, None, 'パプアニューギニア', '中深煎り', None),
    ('81315811', 'コロンビア ポパヤン SUP', 200, None, 'コロンビア', '中深煎り', None),
    ('83852547', 'エチオピア シダモ G2 ウォッシュド カフェインレス', 200, None, 'エチオピア', None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_LABEL_PATTERN = re.compile(r"(?:精製方法|精製処理|精選方法|精選|Process|process)\s*[】:：]?\s*(.{0,12})")
DESC_CUT_MARKERS = ['製造販売者']
DESC_PREFIX = ''
DESC_AFTER = ''
NO_PREFIX_IDS = ()
DESC_MAXLEN = 400

_last_request = [0.0]


def fetch(item_id: str) -> str:
    wait = REQUEST_INTERVAL_SEC - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    _last_request[0] = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def clean_desc(raw: str, item_id: str = "") -> str | None:
    s = html.unescape(raw or "")
    if DESC_AFTER and DESC_AFTER in s:
        s = s.split(DESC_AFTER, 1)[1]
    for marker in DESC_CUT_MARKERS:
        idx = s.find(marker)
        if idx >= 0:
            s = s[:idx]
    s = re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()
    s = (("" if item_id in NO_PREFIX_IDS else DESC_PREFIX) + s).strip()
    return s[:DESC_MAXLEN] or None


def build_record(item_id, name, weight_g, category, origin, roast, process_override) -> dict | None:
    page = fetch(item_id)
    desc_m = DESC_PATTERN.search(page)
    raw_desc = desc_m.group(1) if desc_m else ""
    price_m = PRICE_PATTERN.search(page)
    pm = PURCHASABILITY_PATTERN.search(page)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category:
        parsed["category"] = category
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
        parsed["designated_brand"] = None
    else:
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name"
    process = process_override
    if not process and parsed["category"] != "ブレンド":
        process = parsed["processing_method"]
        if not process:
            for m in PROCESS_LABEL_PATTERN.finditer(html.unescape(raw_desc).replace("\u3000", " ")):
                process = detect_processing_method(m.group(1))
                if process:
                    break

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": process,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": clean_desc(raw_desc, item_id),
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
    for item in ITEMS:
        try:
            record = build_record(*item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_momofukumame.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_momofukumame.json に出力しました")


if __name__ == "__main__":
    main()
