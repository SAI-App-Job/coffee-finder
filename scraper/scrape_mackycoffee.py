# -*- coding: utf-8 -*-
"""
scrape_mackycoffee.py

Macky.coffee(https://mackycoffee.base.shop/、埼玉県川越市連雀町27-1)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-26時点): sitemap.xmlの商品ページ(約30件)から、自家焙煎の焙煎豆のみをITEMSに明示している。
同一銘柄が100g/200g/500gの別ページで並ぶため、最小重量(100g)のページを代表とする。
SCAJコーヒーヴィレッジのリリースロット3種(エクアドル・ペルー2種)は小容量で、エクアドルのみ説明文に「60g」と明記、
ペルー2種は重量の記載が商品ページに無いため weight_g は null(価格のみ取得)。焙煎度の記載も無いため null。
ドリップバッグ・水出しアイスコーヒーバッグ・セット・オリジナルドリップバッグ作製・キャニスター缶・ギフトBOXは除外。
焙煎度は説明文の「Light Roast」「Medium Roast」から取得する。
価格(product:price:amount)・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

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

SHOP_INFO = {   'name': 'Macky.coffee',
    'url': 'https://mackycoffee.base.shop/',
    'platform': 'BASE',
    'address': '埼玉県川越市連雀町27-1',
    'prefecture': '埼玉県',
    'robots_txt_status': '実質許可(他のBASE系店舗と同一の記述。python-requests/curl等は個別にDisallow、User-agent: '
                         '*では許可。識別可能なUser-Agentを使用し、取得間隔は5.5秒)',
    'source_note': 'BASEストア(https://mackycoffee.base.shop/)のsitemap.xmlと各商品ページを2026-10-26に確認。住所は特商法(/law、〒350-0066 '
                   '埼玉県川越市連雀町27-1)。商品に2026年SCAJリリースのロットあり(更新は新しい)',
    'last_verified_at': '2026-10-26'}

BASE_URL = "https://mackycoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.5  # BASE系は5秒以上

# 商品ID, 表示名, 重量(g/不明はNone), カテゴリ(None=自動/"ブレンド"), 原産国(ブレンドはNone), 焙煎度(選択式・不明はNone), 精製方法の上書き(Noneなら説明文から検出)
ITEMS = [
    ('163812717', 'ECUADOR Casa Lumisitana', 60, None, 'エクアドル', None, None),
    ('163813130', 'PERU Neyda Casa', None, None, 'ペルー', None, None),
    ('163813390', 'PERU Gonzalo Montoya', None, None, 'ペルー', None, None),
    ('141980406', 'BRAZIL Vovo Candinha', 100, None, 'ブラジル', '浅煎り', None),
    ('153470820', 'ETHIOPIA Ayla Bombe', 100, None, 'エチオピア', '浅煎り', None),
    ('161532029', 'ETHIOPIA Gogogu Washed', 100, None, 'エチオピア', '浅煎り', None),
    ('156340935', 'HONDURAS Sueno Fertil', 100, None, 'ホンジュラス', '浅煎り', None),
    ('150192366', 'PERU Manuel Elera', 100, None, 'ペルー', '浅煎り', None),
    ('136508204', 'BRAZIL Guariroba', 100, None, 'ブラジル', '中煎り', None),
    ('140191998', '【Decaf】ETHIOPIA Shakiso', 100, None, 'エチオピア', '中煎り', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_LABEL_PATTERN = re.compile(r"(?:精製方法|精製処理|精選方法|精選|Process|process)\s*[】:：]?\s*(.{0,12})")
DESC_CUT_MARKERS = ['※配送について']
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
    with open("data_mackycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mackycoffee.json に出力しました")


if __name__ == "__main__":
    main()
