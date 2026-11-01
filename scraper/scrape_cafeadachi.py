# -*- coding: utf-8 -*-
"""
scrape_cafeadachi.py

カフェ・アダチ(有限会社ニジュウ・イチ企画、岐阜県関市小瀬1833、公式 cafe-adachi.com)の
楽天市場店(www.rakuten.co.jp/cafe-adachi)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店を採用した理由】
同店は楽天市場・Yahoo!ショッピング(store.shopping.yahoo.co.jp/cafe-adachi/)・BASE(cafeadachi.thebase.in)・
Shopify(cafe-adachi-shop.com)に出店している。楽天市場店はショップカテゴリ「ブレンドコーヒー」「ストレートコーヒー」
「季節のコーヒー豆」「美味しいカフェインレスコーヒー」「アイスコーヒー」に豆の単品が揃い(ブレンド3・ストレート10・
季節1・カフェインレス1・アイス1の計16銘柄)、各商品ページの価格が itemprop="price" で確認できるため採用する。
BASEは豆が少数(アダチブレンド800g 等)。Shopify の /products.json はHTTP 429だったため使用しない(取得方法の切替はしない)。
Yahoo!ショッピングは未取得(重複を避けるため楽天に一本化)。

【対象商品について】
楽天市場店の各ページは単品商品(SKUなし、挽き具合は豆のまま/粗挽き/中挽き/細挽きの選択式で価格は共通)。
各銘柄の最小重量の商品を代表とする(通常200g、パナマ・ゲイシャのみ100g)。同じ銘柄の800g(まとめ買い)ページと
パナマ・ゲイシャ200gは重量違いの重複として除外。除外: 飲み比べ・お試し・詰め合わせセット(200bs4, bs-6000)、
ドリップバッグ(sid15, sid28)、カフェオレのもと、リキッド・水出しアイスコーヒー(i-02, i-03, ice-3, liq5home, miz5, miz15, lipmoto5)、ギフト。
在庫は商品ページの itemprop="availability" で判定。焙煎度は商品説明に明記のあるもの(深煎り・中深煎り)のみ。
焙煎機: 商品ページの店舗紹介に「焙煎は、最新型のドイツ製プロバット焙煎機を駆使します」とある。
販売業者: 有限会社ニジュウ・イチ企画 岐阜県関市小瀬1833(楽天の会社概要)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "カフェ・アダチ",
    "url": "https://www.rakuten.co.jp/cafe-adachi/",
    "platform": "楽天市場",
    "address": "岐阜県関市小瀬1833",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可とみなす(2026-11-01確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/cafe-adachi/)のカテゴリ(ブレンド・ストレート・季節・カフェインレス・アイス)と各商品ページを2026-11-01に確認。"
                   "他の出店先(Yahoo!ショッピング・BASE・Shopify)は重複を避け不採用。季節ブレンドは冬限定",
    "last_verified_at": "2026-11-01",
}

SHOP_ID = "cafe-adachi"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, 産地(Noneはブレンド), 焙煎度(商品説明に明記があるもの), 重量g)
ITEMS = [
    ("b-007", "アダチブレンド", None, None, 200),
    ("b-005", "イタリアンブレンド", None, "深煎り", 200),
    ("b-13", "刀匠ブレンド", None, None, 200),
    ("xb200", "冬限定 クリスマスブレンド", None, "深煎り", 200),
    ("ice200", "アイスコーヒー", None, "深煎り", 200),
    ("bra200", "ブラジル No.2", "ブラジル", None, 200),
    ("col200", "コロンビア ウィラ スイート", "コロンビア", "深煎り", 200),
    ("gua200", "グァテマラ アンティグア", "グアテマラ", None, 200),
    ("keny200", "ケニア AA", "ケニア", "深煎り", 200),
    ("man200", "マンデリン シボルガ", "インドネシア", "深煎り", 200),
    ("mex200", "メキシコ マヤビニック 有機栽培", "メキシコ", None, 200),
    ("moca200", "エチオピア イルガチェフ", "エチオピア", "中深煎り", 200),
    ("panamag100", "パナマ ゲイシャ", "パナマ", None, 100),
    ("peo200", "ペルー 有機栽培", "ペルー", "中深煎り", 200),
    ("tanz200", "タンザニア キリマンジャロ スノートップ", "タンザニア", None, 200),
    ("sida200", "エチオピア シダモ カフェインレス", "エチオピア", "深煎り", 200),
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


def item_description(html_text: str) -> str | None:
    """商品固有の説明(「不適切な商品を報告」以降〜「【挽き具合を選べます】」まで)。"""
    el = BeautifulSoup(html_text, "html.parser").select_one(".sale_desc")
    if not el:
        return None
    txt = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", el.get_text(" ")))
    k = txt.find("不適切な商品を報告")
    if k < 0:
        return None
    body = txt[k + len("不適切な商品を報告"):]
    body = body.split("【挽き具合を選べます】")[0].strip()
    return body[:400] or None


def build_record(code: str, name: str, origin: str | None, roast: str | None, weight: int) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    m = PRICE_PATTERN.search(html_text)
    if not m:
        print(f"[warn] 価格取得失敗: {code} {name}")
        return None
    price = int(m.group(1))
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": item_description(html_text),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, item in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(*item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafeadachi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafeadachi.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
