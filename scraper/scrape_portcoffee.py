# -*- coding: utf-8 -*-
"""
scrape_portcoffee.py

PO-RT COFFEE(https://portcoffee.theshop.jp/、埼玉県ふじみ野市上福岡4-6-11)の商品情報を取得する。BASE(THE SHOP)。

【対象商品について】
実データ確認済み(2026-10-26時点): sitemap.xmlの商品ページ(29件)から、焙煎豆10商品(うち1商品はセール品で完売)のみを対象とする。
各商品は100g(基本価格)/200g(+上乗せ)と、浅煎り・中煎り・深煎りの焙煎度、豆のまま/挽きを選択できる。
最小重量の100gの基本価格を採用。焙煎度は選択式のため null とし、説明文の頭に選択肢を明記する(PO-RT Blendは深煎り固定)。
ドリップバッグ(バラ・3個セット・10個セット)は除外。
説明文は「テイスティングノート」以降(焙煎度別の味わい)を採用する。

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

SHOP_INFO = {   'name': 'PO-RT COFFEE',
    'url': 'https://portcoffee.theshop.jp/',
    'platform': 'BASE',
    'address': '埼玉県ふじみ野市上福岡4-6-11',
    'prefecture': '埼玉県',
    'robots_txt_status': '実質許可(他のBASE系店舗と同一の記述。python-requests/curl等は個別にDisallow、User-agent: '
                         '*では許可。識別可能なUser-Agentを使用し、取得間隔は5.5秒)',
    'source_note': 'THE '
                   'SHOP(BASE系、https://portcoffee.theshop.jp/)のsitemap.xml・各商品ページ・/about・ACCESS(/p/00002、埼玉県ふじみ野市上福岡4-6-11、10:00〜18:00、毎週水曜定休)を2026-10-26に確認。食べログ(https://tabelog.com/saitama/A1103/A110302/11068015/)でも同住所。aboutに「ご注文いただいてから必要な分を焙煎」とあり。新ブレンド・2025〜2026年のロット追加あり(更新は新しい)',
    'last_verified_at': '2026-10-26'}

BASE_URL = "https://portcoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5  # BASE系は5秒以上

# 商品ID, 表示名, 重量(g/不明はNone), カテゴリ(None=自動/"ブレンド"), 原産国(ブレンドはNone), 焙煎度(選択式・不明はNone), 精製方法の上書き(Noneなら説明文から検出)
ITEMS = [
    ('163174282', 'コスタリカ カンデリージャ農園 ハニーティピカ', 100, None, 'コスタリカ', None, 'ハニー'),
    ('154247197', 'グアテマラ フライハーネス SHB ブルボンの苗木プロジェクト', 100, None, 'グアテマラ', None, None),
    ('143340136', 'パプアニューギニア マッドマンコーヒー ウォッシュ A', 100, None, 'パプアニューギニア', None, 'ウォッシュド'),
    ('130429570', 'PO-RT Blend', 100, 'ブレンド', None, '深煎り', None),
    ('126227807', 'ドミニカ ワイニーナチュラル', 100, None, 'ドミニカ共和国', None, 'ナチュラル'),
    ('123199850', 'ペルー ホワイトコンドル', 100, None, 'ペルー', None, None),
    ('119584032', 'エルサルバドル マラカラ ブルボン', 100, None, 'エルサルバドル', None, None),
    ('119462892', 'メキシコ チアパス カフェインレス', 100, None, 'メキシコ', None, None),
    ('115012490', 'インドネシア マンデリン シナール', 100, None, 'インドネシア', None, None),
    ('114442232', 'エチオピア ゲイシャ G-3 ナチュラル(開店記念セール)', 100, None, 'エチオピア', None, 'ナチュラル'),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_LABEL_PATTERN = re.compile(r"(?:精製方法|精製処理|精選方法|精選|Process|process)\s*[】:：]?\s*(.{0,12})")
DESC_CUT_MARKERS = ['※初めて']
DESC_PREFIX = '焙煎度は浅煎り・中煎り・深煎りから選択(価格は100g)。'
DESC_AFTER = '＜テイスティングノート＞'
NO_PREFIX_IDS = ('130429570',)
DESC_MAXLEN = 450

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
    with open("data_portcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_portcoffee.json に出力しました")


if __name__ == "__main__":
    main()
