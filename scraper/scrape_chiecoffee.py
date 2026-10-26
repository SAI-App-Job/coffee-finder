# -*- coding: utf-8 -*-
"""
scrape_chiecoffee.py

ChieCoffee(https://chiecoffee.thebase.in/、埼玉県ふじみ野市上福岡1-2-16)の商品情報を取得する。BASE。

【住所について】
BASEの特商法ページはBASE社の住所のため使えない。番地までは食べログ(https://tabelog.com/saitama/A1103/A110302/11042081/)の
掲載住所に依拠。自店about(/about)・公式ブログ(finecafe.exblog.jp)ではふじみ野市上福岡までしか確認できない。

【対象商品について】
実データ確認済み(2026-10-26時点): 豆11商品(すべて100g)。期間限定のハロウィンブレンド(10/29ご注文分まで)を含む。
ドリップバッグ詰め合わせは除外。「豆」か「粉」を選べるが豆のままの価格(同額)。
焙煎度は説明文冒頭の【ハイロースト】【シティロースト】【フルシティロースト】から取得(記載の無い商品は null)。
「水出し珈琲」は用途専用の豆で配合は未記載のため、ブレンドとして扱った(推定)。
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

SHOP_INFO = {   'name': 'ChieCoffee',
    'url': 'https://chiecoffee.thebase.in/',
    'platform': 'BASE',
    'address': '埼玉県ふじみ野市上福岡1-2-16',
    'prefecture': '埼玉県',
    'robots_txt_status': '実質許可(他のBASE系店舗と同一の記述。python-requests/curl等は個別にDisallow、User-agent: '
                         '*では許可。識別可能なUser-Agentを使用し、取得間隔は5.5秒)',
    'source_note': 'BASEストア(https://chiecoffee.thebase.in/)のsitemap.xmlと各商品ページ、/aboutを2026-10-26に確認。住所は食べログ(https://tabelog.com/saitama/A1103/A110302/11042081/)掲載値(番地)。自店aboutで「ふじみ野市上福岡で、テイクアウト専門のコーヒースタンド」「自家焙煎珈琲豆屋」を確認。ハロウィンブレンドが10/29ご注文分までの販売(更新は新しい)',
    'last_verified_at': '2026-10-26'}

BASE_URL = "https://chiecoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5  # BASE系は5秒以上

# 商品ID, 表示名, 重量(g/不明はNone), カテゴリ(None=自動/"ブレンド"), 原産国(ブレンドはNone), 焙煎度(選択式・不明はNone), 精製方法の上書き(Noneなら説明文から検出)
ITEMS = [
    ('34214945', 'ハロウィンブレンド(期間限定・10/29ご注文分まで)', 100, 'ブレンド', None, None, None),
    ('161894856', 'インドネシア マンデリン ビンタンリマ', 100, None, 'インドネシア', None, None),
    ('150870969', 'ウガンダ マウントエルゴン カプチョルワ ウォッシュ', 100, None, 'ウガンダ', None, None),
    ('117797129', '陽だまりに香る朝の珈琲', 100, 'ブレンド', None, 'ハイロースト', None),
    ('72412604', 'エチオピア イルガチェフェ ブナブナ ナチュラル', 100, None, 'エチオピア', 'ハイロースト', None),
    ('93989610', '牛乳に寄り添う珈琲', 100, 'ブレンド', None, 'フルシティロースト', None),
    ('94318848', '【デカフェ】コスタリカ ジャガー ハニー', 100, None, 'コスタリカ', 'ハイロースト', None),
    ('8051821', 'グアテマラ アンティグア SHB', 100, None, 'グアテマラ', 'ハイロースト', None),
    ('8051796', 'コロンビア スウィートベリー SUP', 100, None, 'コロンビア', 'シティロースト', None),
    ('1779753', 'ブラジル サントアントニオ プレミアムショコラ', 100, None, 'ブラジル', None, None),
    ('11209896', 'まろやかに広がる味わいの水出し珈琲', 100, 'ブレンド', None, 'フルシティロースト', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_LABEL_PATTERN = re.compile(r"(?:精製方法|精製処理|精選方法|精選|Process|process)\s*[】:：]?\s*(.{0,12})")
DESC_CUT_MARKERS = ['※※※お読みください※※※']
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
    with open("data_chiecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chiecoffee.json に出力しました")


if __name__ == "__main__":
    main()
