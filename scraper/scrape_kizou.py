# -*- coding: utf-8 -*-
"""
scrape_kizou.py

コーヒーショップ 喜蔵(Coffeeshop喜蔵＆はらだ酒店、佐賀県武雄市武雄町武雄7353)の楽天市場店
(www.rakuten.co.jp/kizou-h)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【店舗の確認(2026-11-03)】
実店舗は武雄温泉通りの「コーヒーショップ 喜蔵」(佐賀県武雄市武雄町武雄7353、TEL 0954-22-2662、
https://www.kashimacity.com/eat/kizou/index.html に「自家焙煎コーヒー 楼門ブレンド 100g 800円~」)。
運営は老舗酒屋「はらだ酒店」(楽天の会社概要の所在地は武雄市山内町三間坂甲13209-2)で、
実店舗の所在地(武雄町武雄7353)を住所に採用する。ショップトップに「創業明治19年、老舗の酒屋が始めた
自家焙煎珈琲のお店です」。楽天以外の独自ECは無い(公式は旧ブログ kizou.sagafan.jp のみ)。

【対象商品について】
同じ銘柄が容量別(100g/200g/400g/1kg)に別ページ(商品コード末尾 100/300/500/1000)で並ぶ。
各銘柄の最小重量(原則100g)のページを代表とし、重複は統合する。
100gの無いタンザニア(キボAA)とペルー(モンテアルト農園、品切れ中)は200gを採用する。
単品ページのためSKUは無く、価格は itemprop="price"、在庫は itemprop="availability" から取る。
除外: ドリップバッグ、水出し、チョコビーンズ、大豆ブレンド(カフェインレス大豆コーヒー)、
お試し5種セット・ギフト、200g以上のページ(同銘柄の100gがあるもの)、1kg。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "コーヒーショップ 喜蔵",
    "url": "https://www.rakuten.co.jp/kizou-h/",
    "platform": "楽天市場",
    "address": "佐賀県武雄市武雄町武雄7353",
    "prefecture": "佐賀県",
    "robots_txt_status": "実質許可とみなす(2026-11-03確認。item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)のみ禁止。www.rakuten.co.jpは/com/ /shops/等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/kizou-h/)のショップカテゴリ(100グラム/200グラム/産地別)と各商品ページを2026-11-03に確認。ショップ内ランキング更新日2026-11-02。実店舗の住所は鹿島市/武雄市観光サイト・食べログ",
    "last_verified_at": "2026-11-03",
}

SHOP_ID = "kizou-h"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, 重量g, 産地(Noneはブレンド), 焙煎度(商品ページに明記があるもののみ))
ITEMS = [
    ("rommon100", "武雄温泉 楼門ブレンド", 100, None, None),
    ("mocamoca100", "モカモカ モカブレンド", 100, None, None),
    ("santos100", "ブラジル サントス No.2", 100, "ブラジル", None),
    ("elsal100", "ブラジル ショコラ サンアントニオ農園", 100, "ブラジル", None),
    ("suplemo100", "コロンビア ウイラ スプレモ", 100, "コロンビア", "中煎り"),
    ("10000111-100", "コロンビア エメラルドマウンテン", 100, "コロンビア", None),
    ("ethiopia100", "エチオピア モカ イルガチェフ G2 ウォッシュド", 100, "エチオピア", "中煎り"),
    ("ethiopia-g3-100", "エチオピア ゲイシャ グジ ゲレザ G-3 ナチュラル", 100, "エチオピア", None),
    ("guatemala100", "グアテマラ ウエウエテナンゴ パルミラ", 100, "グアテマラ", None),
    ("iemen100", "イエメン モカ マタリ No.9", 100, "イエメン", None),
    ("kilimanjaro100", "インドネシア マンデリン G1", 100, "インドネシア", None),
    ("papua100", "パプアニューギニア シグリ AA", 100, "パプアニューギニア", None),
    ("rwanda100", "ルワンダ スカイヒル ウォッシュド", 100, "ルワンダ", None),
    ("10000010-100", "メキシコ オーガニック カフェインレス デカフェ", 100, "メキシコ", None),
    ("tanzania300", "タンザニア キボ AA", 200, "タンザニア", None),
    ("peru200", "ペルー モンテアルト農園 JAS オーガニック", 200, "ペルー", None),
]

_first = True


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def build_record(code, name, weight, origin, roast):
    global _first
    if not _first:
        time.sleep(REQUEST_INTERVAL)
    _first = False
    url = ITEM_URL.format(code=code)
    resp = fetch(url)
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
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list:
    records = []
    for item in ITEMS:
        rec = build_record(*item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kizou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kizou.json に出力しました")


if __name__ == "__main__":
    main()
