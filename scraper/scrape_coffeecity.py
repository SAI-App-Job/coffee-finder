# -*- coding: utf-8 -*-
"""
scrape_coffeecity.py

コーヒーシティ(屋号「珈琲豆専門店コーヒーシティ」「コーヒー・シティ」、山口県周南市楠木1丁目8-1、代表 貞森恒男)の
Yahoo!ショッピング店(store.shopping.yahoo.co.jp/coffee-city)の商品情報を取得する。

【Yahoo!ショッピング店を採用した理由】
同店は楽天市場店(item.rakuten.co.jp/coffee-city/)にも出店している。楽天はストレート11件・ブレンド8件で、重量違いを
SKUにまとめた構成。Yahoo!は重量ごとに別商品ページ(例: s10001=100g、s-001=200g)があり、全122件(ストレート55・ブレンド21)と
品目が多い(神山ハニー・Qグレード各種・ブルーマウンテン等は楽天のストレートカテゴリに見当たらない)ため、Yahoo!を採用した。

【実店舗・自家焙煎の根拠(2026-10-20確認)】
 - Yahoo!ショッピング会社概要: 住所 山口県周南市楠木1丁目8ー1、代表者 貞森恒男、TEL 0834-28-9639、
   ストア紹介「直火焙煎という焙煎方式で、より味わい深いコーヒーを追求しています」。
 - 周南市企業データベース(shunan-marketing.jp/CP/1/664/): 「珈琲豆専門店 コーヒー・シティ」周南市楠木1丁目8-1、
   事業内容は珈琲豆小売、主要サービスに「コーヒー豆の焙煎、販売、宅配、発送」。
 - 楽天市場店タイトルに「自家焙煎の珈琲豆を扱うお店です」、商品名に【自家焙煎】【直火焙煎】。
 ※「店で焙煎」の第三者による明確な記載は取れず、自家焙煎は店自身の申告と企業DBの「焙煎」で確認(やや弱い根拠)。

【対象商品について】
ストレート・ブレンドのうち、各銘柄の最小重量の単品(通常100g)の豆。セット、お試し、20g少量、ドリップ/ティーバッグ、
ギフト、アイスリキッド、ゼリーは除外。100gが無い銘柄(Qグレード系・ブルーマウンテン等)は最小重量(200g〜600g)を採用。
焙煎度は商品ページに記載が無いため、商品名/楽天の商品タグにあるもののみ設定。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "コーヒーシティ",
    "url": "https://store.shopping.yahoo.co.jp/coffee-city/",
    "platform": "Yahoo!ショッピング",
    "address": "山口県周南市楠木1丁目8-1",
    "prefecture": "山口県",
    "robots_txt_status": "未確認(Yahoo!ショッピングストアのrobots.txtは404。/search.htmlと各商品ページのみ使用)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/coffee-city/)の商品一覧(全122件)・各商品ページを2026-10-20に確認。"
                   "住所はYahoo!の会社概要と周南市企業データベース。自家焙煎は店の申告(直火焙煎・楽天店の自家焙煎表記)と企業DBの焙煎業務で確認",
    "last_verified_at": "2026-10-20",
}

STORE = "coffee-city"
BASE = f"https://store.shopping.yahoo.co.jp/{STORE}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 3
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# (商品コード, 商品名, 重量g, 産地(Noneは判定不可 or ブレンド), ブレンドか, 焙煎度)
ITEMS = [
    ("s10001", "コロンビア・スプレモ", 100, "コロンビア", False, None),
    ("s10002", "ブラジル・サントス", 100, "ブラジル", False, None),
    ("s10003", "ハイクォリティ・グァテマラ", 100, "グアテマラ", False, None),
    ("s10005", "タンザニアQグレード スノートップAA(キリマンジャロ)", 100, "タンザニア", False, None),
    ("s10006", "クィーン・スマトラ(スーパーマンデリン)", 100, "インドネシア", False, None),
    ("s10007", "モカ(シダモ ウォッシュド)", 100, "エチオピア", False, None),
    ("s10008", "グァテマラQグレード パストレス農園", 100, "グアテマラ", False, None),
    ("s10009", "モカ・マタリ", 100, "イエメン", False, None),
    ("s10010", "バリ神山ハニー", 100, "インドネシア", False, None),
    ("s10011", "トラジャ・ランテカルア スロトコ農園", 100, "インドネシア", False, None),
    ("s10014", "ペルーQグレード マチュピチュ", 100, "ペルー", False, None),
    ("b10001", "スペシャルブレンド", 100, None, True, None),
    ("b10002", "マイルドブレンド", 100, None, True, None),
    ("b10003", "ヨーロピアンブレンド", 100, None, True, "フレンチロースト"),
    ("b10004", "アイスブレンド", 100, None, True, "深煎り"),
    ("b10005", "モカブレンド", 100, None, True, "フルシティロースト"),
    ("b10006", "シティブレンド", 100, None, True, None),
    ("b10007", "ハイブレンド", 100, None, True, "フルシティロースト"),
    ("b10009", "オリジナルブレンド", 100, None, True, None),
    ("cho100", "長州の香", 100, None, True, "深煎り"),
    ("brqg003", "ブラジルQグレード マンチケーラ(サンタルジア農園)", 300, "ブラジル", False, None),
    ("rmq300", "ルビーマウンテンQグレード", 300, None, False, None),
    ("pap300", "パプアニューギニアQグレード", 300, "パプアニューギニア", False, None),
    ("mguji300", "モカ・グジ ナチュラル G4+", 300, "エチオピア", False, None),
    ("elsal300", "エルサルバドルQグレード ジュリア", 300, "エルサルバドル", False, None),
    ("sakura500", "限定ブラジルさくらブルボン(サンタルジア農園)", 500, "ブラジル", False, None),
    ("domi600g", "ドミニカAAバラオナ", 600, "ドミニカ共和国", False, "浅煎り"),
    ("bule200", "ブルーマウンテンNo.1", 200, "ジャマイカ", False, None),
    ("crys200", "クリスタルマウンテン", 200, "キューバ", False, None),
]


def fetch_item(code):
    url = f"{BASE}{code}.html"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
    item = json.loads(m.group(1))["props"]["pageProps"]["item"]
    desc = item.get("catchCopy") or None
    return url, item.get("applicablePrice"), bool((item.get("stock") or {}).get("isAvailable", True)), desc, item.get("name")


def build_record(code, name, weight, origin, blend, roast):
    time.sleep(CRAWL_DELAY_SECONDS)
    url, price, available, desc, page_name = fetch_item(code)
    m = re.search(r"(\d+)\s*[gｇ]", page_name or "")
    page_weight = int(m.group(1)) if m else None
    if page_weight != weight:
        print(f"[warn] 重量不一致 {code}: 設定{weight} / ページ{page_weight}")
    parsed = parse_product(name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "shop_attribute" if origin else None
    out = not available
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,  # 商品名の「ハイ」「シティ」はブランド名なので parse_product の焙煎度は使わない
        "roast_hint": None,
        "flavor_notes": re.sub(r"^直火焙煎\s*", "", desc) if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    records = [build_record(*i) for i in ITEMS]
    with open("data_coffeecity.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeecity.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
