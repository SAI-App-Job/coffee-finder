# -*- coding: utf-8 -*-
"""
scrape_okanouecoffee.py

丘の上珈琲(珈琲考房、北海道夕張郡長沼町加賀団体、運営 株式会社シーボルト)の楽天市場店
(www.rakuten.co.jp/ko-hi-koubou/)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店を採用した理由】
公式サイト okanoue-coffee.com の「ONLINE SHOP」に楽天市場とYahoo!ショッピングのリンクがあるが、
Yahoo!ショッピングのストア(store.shopping.yahoo.co.jp/ko-hi-koubou/)は閉鎖済みで、楽天市場店のみ有効。

【対象商品について】
ショップカテゴリ「オリジナルブレンド」「シングルオリジン」「季節のブレンド」「アイスコーヒー用の珈琲豆」の
豆単品のうち、各銘柄の最小重量=100g(1xxx100 / 2xxx100)の価格を代表とする(豆・粉の選択は同価格のオプションで、
豆のままを採用)。各銘柄に 200g/300g/500g(250g×2)/1kg 等の別ページ、保存缶付き(-l1)がある。
除外: ドリップバッグ、ギフト、セット(丘の上ブレンドセット等)、有機農園セット、飲み比べ、保存缶付き、大容量。
 - 2005100 と 200510 はマンデリン100gの同一内容の重複ページのため 2005100 のみ。
 - 商品ページには SKU が無い単品(商品ページの価格 itemprop="price")。
 - 焙煎度は商品ページに明記があるのはフレンチブレンド(「当店で唯一の深煎り」)とアイスコーヒー用(深煎り)のみ。他は null。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "丘の上珈琲",
    "url": "https://www.rakuten.co.jp/ko-hi-koubou/",
    "platform": "楽天市場",
    "address": "北海道夕張郡長沼町加賀団体",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/ko-hi-koubou/)のショップカテゴリと各商品ページを2026-10-20に確認。"
                   "公式サイト(https://okanoue-coffee.com/)に「丘の上珈琲(珈琲考房)」の住所〒069-1316 夕張郡長沼町加賀団体・営業時間11:00-17:00・2F 20席の喫茶・「自家焙煎で丁寧に焼き上げた豆」と記載。"
                   "番地は公式・食べログ・楽天のいずれにも記載が無く、字(加賀団体)までを採用",
    "last_verified_at": "2026-10-20",
}

SHOP_ID = "ko-hi-koubou"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, ブレンドの配合国(単一産地はNone), 産地(ブレンドはNone), 焙煎度)
ITEMS = [
    ("1001100", "サワーブレンド", ["ブラジル", "コロンビア", "タンザニア"], None, None),
    ("1002100", "ライトブレンド", ["ブラジル", "コロンビア", "エチオピア", "グアテマラ"], None, None),
    ("1003100", "ソフトブレンド", ["ブラジル", "コロンビア", "エチオピア"], None, None),
    ("1004100", "ビターブレンド", ["ブラジル", "コロンビア", "インドネシア"], None, None),
    ("1005100", "フレンチブレンド", ["ブラジル", "コロンビア", "エチオピア"], None, "深煎り"),
    ("1006100", "アイスコーヒー用ブレンド", ["ブラジル", "コロンビア", "エチオピア"], None, "深煎り"),
    ("1007100", "季節限定 秋ブレンド", [], None, None),
    ("2001100", "ブラジル セーハ・トレス・バハス", None, "ブラジル", None),
    ("2002100", "コロンビア ビジャ・ファティマ ブルボン", None, "コロンビア", None),
    ("2003100", "エチオピア イルガチェフェ G-1", None, "エチオピア", None),
    ("2004100", "タンザニア モンデュール", None, "タンザニア", None),
    ("2005100", "インドネシア マンデリン ポルンアルフィナ", None, "インドネシア", None),
    ("2006100", "コスタリカ カンデリージャハニー", None, "コスタリカ", None),
    ("2007100", "グアテマラ", None, "グアテマラ", None),
    ("2009100", "エルサルバドル エル レクエルド ブルボン ハニー", None, "エルサルバドル", None),
    ("2010100", "エクアドル ガラパゴス サンタクルス", None, "エクアドル", None),
    ("2011100", "ラオス ティピカ", None, "ラオス", None),
]


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def build_record(code, name, comps, origin, roast, html_text):
    price_m = PRICE_PATTERN.search(html_text)
    if not price_m:
        print(f"[warn] 価格取得失敗: {code} {name}")
        return None
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"
    soup = BeautifulSoup(html_text, "html.parser")
    desc_el = soup.select_one("span.sale_desc")
    desc = desc_el.get_text(" ", strip=True) if desc_el else None
    if not desc:
        og = soup.select_one('meta[property="og:description"]')
        desc = (og["content"].split("。。")[0] if og and og.get("content") else None)
    if desc:
        desc = re.sub(r"豆・粉、?どちらもお選びいただけます。*", "", re.sub(r"\s+", " ", desc)).strip()[:300] or None

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
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
        "roast_level": roast,  # 商品名の「ライト」等はブレンド名で焙煎度ではないため、商品ページに明記された値のみ
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [{"origin_country": c} for c in (comps or [])],
        "price": int(price_m.group(1)),
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list:
    records = []
    for i, (code, name, comps, origin, roast) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        resp = fetch(ITEM_URL.format(code=code))
        if resp.status_code != 200:
            print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
            continue
        rec = build_record(code, name, comps, origin, roast, resp.text)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_okanouecoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_okanouecoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:40])


if __name__ == "__main__":
    main()
