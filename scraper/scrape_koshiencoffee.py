# -*- coding: utf-8 -*-
"""
scrape_koshiencoffee.py

自家焙煎珈琲 珈嗜園(こうしえん、楽天店名 Koshien Coffee Roasters、兵庫県西宮市甲子園網引町2-17)の
楽天市場店(www.rakuten.co.jp/koshien)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店の特徴(要注意)】
店は全439件(2026-10-20)で、同じ銘柄が重量違い・価格違いの別商品ページとして何十件も並ぶ
(例: 珈嗜園ブレンドだけで80g/90g/100g/110g/300g/400g/440g/500g…が別ページ)。さらに福袋・飲み比べ・業務用・
麻袋・コカ・コーラ等が混在する。メール便の少量品は「1,000円(送料込み)で50〜120g」のように価格を揃えて
重量を変えた設定が多く、重量と価格の関係が一定でない。
【採用方針】
銘柄(焙煎度違いは別銘柄)ごとに、タイトルに重量が明記された最小重量の単品ページを代表1件とする(100gより小さい
50〜90gも最小重量を採用する)。除外: 福袋・飲み比べ・「お好きな組み合わせ」セット・業務用/オフィス向け・
500g以上の大容量・ドリップ・コカ・コーラ・アイスコーヒー液等。重量の下限と異なる別ページが同一銘柄で多数あるため、
銘柄単位の最小重量ページを手で選んだ(ITEMSの商品コード)。タイトルの重量表記を weight_g に使う。
1935ブレンド(1935_200-2)のみSKU(240g/500g/720g)があり最小の240gを採用。
価格は税込(送料込み表記が多い)。在庫は itemprop="availability"。
販売業者(特定商取引法): 自家焙煎珈琲 珈嗜園(代表 吉岡勉) 兵庫県西宮市甲子園網引町2-17。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "自家焙煎珈琲 珈嗜園",
    "url": "https://www.rakuten.co.jp/koshien/",
    "platform": "楽天市場",
    "address": "兵庫県西宮市甲子園網引町2-17",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店Koshien Coffee Roasters(https://www.rakuten.co.jp/koshien/)の全カテゴリ一覧と各商品ページを2026-10-20に確認。"
                   "住所・営業時間(10〜18時、日曜・第2/4月曜休み)は楽天の会社概要、Retty(https://retty.me/area/PRE28/ARE103/SUB10301/100001660663/)の"
                   "店舗情報(コーヒー専門店、同住所・同電話)と一致。同銘柄が重量違いの別ページで多数並ぶため、銘柄ごとの最小重量ページを代表に採用",
    "last_verified_at": "2026-10-20",
}

SHOP_ID = "koshien"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, 産地(None=産地不明またはブレンド), ブレンドか, 焙煎度(商品タイトルの表記))
ITEMS = [
    ("brazil100_2", "ブラジル", "ブラジル", False, None),
    ("10001154", "ブラジル 深煎り(アイスコーヒー・エスプレッソ用)", "ブラジル", False, "深煎り"),
    ("brazil-cinnamonroast_200", "ブラジル 浅煎り", "ブラジル", False, "浅煎り"),
    ("10000002", "コロンビア", "コロンビア", False, None),
    ("10000001", "モカ", None, False, None),
    ("honduras_100-3_2", "ホンジュラス", "ホンジュラス", False, None),
    ("honduras-cinnamonroast_100-4", "ホンジュラス 浅煎り", "ホンジュラス", False, "浅煎り"),
    ("mandheling2", "マンデリン", "インドネシア", False, "深煎り"),
    ("ethiopia-geshavillagecoffee2_3", "エチオピア グジ ゲレザ ゲイシャ ナチュラル", "エチオピア", False, "中深煎り"),
    ("ethiopia-geshavillage2cinnamon2", "エチオピア グジ ゲレザ ゲイシャ ナチュラル 浅煎り", "エチオピア", False, "浅煎り"),
    ("ice-160guatemala", "グアテマラ 深煎り", "グアテマラ", False, "深煎り"),
    ("hondurasblend_150-2_2", "ホンジュラスブレンド", None, True, None),
    ("honduras-frenchroast-ble_100-4_2", "ホンジュラス 深煎りブレンド", None, True, "深煎り"),
    ("mochablend_200-2", "モカブレンド", None, True, None),
    ("man-ble80", "マンデリンブレンド", None, True, "深煎り"),
    ("reiwa-blend_50-4", "令和ブレンド", None, True, None),
    ("koshien70", "珈嗜園ブレンド", None, True, "中深煎り"),
    ("nigo_200-2_2", "第弐珈嗜園ブレンド", None, True, None),
    ("1964_200", "1964ブレンド マンデリンベース", None, True, None),
    ("toushi-120", "闘志ブレンド", None, True, "深煎り"),
    ("iceblend-120", "アイスコーヒーブレンド", None, True, "深煎り"),
    ("1935_200-2", "1935ブレンド", None, True, "中深煎り"),
]


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def extract_skus(html_text: str) -> list[dict]:
    """ページに埋め込まれた "sku":[...] のJSON配列を括弧対応で切り出す。"""
    i = html_text.find('"sku":[')
    if i < 0:
        return []
    start = i + len('"sku":')
    depth, in_str, esc = 0, False, False
    for k in range(start, len(html_text)):
        ch = html_text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html_text[start:k + 1])
    return []


def sku_weight(sku: dict):
    for v in sku.get("selectorValues") or []:
        m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", v).lower())
        if m and "×" not in v:
            return int(m.group(1))
    return None


def build_record(code, name, origin, blend, roast):
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    title = unicodedata.normalize("NFKC", soup.title.get_text(strip=True)) if soup.title else ""

    skus = [(sku_weight(s), s) for s in extract_skus(html_text)]
    skus = [(w, s) for w, s in skus if w]
    if skus:
        weight, sku = min(skus, key=lambda x: x[0])
        price = int(sku["taxIncludedPrice"])
    else:
        m = PRICE_PATTERN.search(html_text)
        if not m:
            print(f"[warn] 価格取得失敗: {code} {name}")
            return None
        price = int(m.group(1))
        wm = re.search(r"(\d+)\s*g", title)  # タイトルの重量表記
        if not wm:
            print(f"[warn] 重量取得失敗: {code} {name}")
            return None
        weight = int(wm.group(1))
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "shop_attribute"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list:
    records = []
    for i, (code, name, origin, blend, roast) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(code, name, origin, blend, roast)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_koshiencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_koshiencoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
