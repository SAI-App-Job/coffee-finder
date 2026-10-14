# -*- coding: utf-8 -*-
"""
scrape_kastnercoffee.py

カフェ・ケストナー(Café Kastner、自家焙煎珈琲 カフェ・ケストナー、店主 佐藤文昭、徳島県徳島市川内町大松255-3、
楽天市場店 www.rakuten.co.jp/cafe-kastner、公式サイト cafe-kastner.com)の楽天市場店の商品情報を取得する。
楽天市場(item.rakuten.co.jp、UTF-8)。

【住所について】
実データ確認済み(2026-10-15): 楽天市場の特定商取引法表記(info.html)は「〒771-0131 徳島県徳島市川内町大松255-3」。
公式サイトの店舗案内(cafe-kastner.com/realshop/)は「徳島市川内町大松255-3-11」(末尾に枝番「-11」が付く)。

【対象商品について】
実データ確認済み(2026-10-15): 店舗の全商品カテゴリ(item.rakuten.co.jp/cafe-kastner/c/0000000001/)に
並ぶコーヒー豆は商品コード cf10000〜cf10028 の24商品(欠番 cf10001/09/12/18/19 は404の削除済み)。
いずれも内容量100gの単品で、「豆のまま/ペーパー用/サイフォン用…」の挽き方は同一商品の選択肢。
ブレンド5・シングル19(ゲイシャ2含む)。アイスコーヒーブレンドも豆の商品として収録。
価格は税込(アイスコーヒーブレンドは送料込み)。商品名・焙煎度・産地は商品ページの表記
(商品名・商品説明の「原産国」「原材料」、画像alt、説明文の焙煎の記述)を確認した上で下のITEMSに
明示している。焙煎度が商品名・説明のどこにも記載されていない銘柄はnullとする。

【robots.txtについて】
楽天市場のrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止で、商品ページは通常のGETで取得できる
(他の楽天市場系スクレイパーと同一の判断)。リクエスト間隔を空ける。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "カフェ・ケストナー",
    "url": "https://www.rakuten.co.jp/cafe-kastner/",
    "platform": "楽天市場",
    "address": "徳島県徳島市川内町大松255-3",
    "prefecture": "徳島県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "cafe-kastner"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.0

# (商品コード, 商品名, ブレンドか, 産地(国名。ブレンドはNone), 焙煎度(記載なしはNone))
ITEMS = [
    ("cf10024", "アイスコーヒーブレンド", True, None, None),
    ("cf10025", "イタリアンブレンド", True, None, "深煎り"),
    ("cf10026", "ケストナーブレンド", True, None, "中深煎り"),
    ("cf10027", "マイルドブレンド", True, None, None),
    ("cf10028", "ソフトブレンド", True, None, "浅煎り"),
    ("cf10000", "インディア APAA", False, "インド", "深煎り"),
    ("cf10002", "エチオピア シダモW", False, "エチオピア", "深煎り"),
    ("cf10003", "マラウィ", False, "マラウイ", "深煎り"),
    ("cf10004", "ペルー エキセルソ", False, "ペルー", "深煎り"),
    ("cf10005", "スマトラ・マンデリン", False, "インドネシア", "深煎り"),
    ("cf10017", "パナマ SHB", False, "パナマ", "中煎り"),
    ("cf10006", "コロンビア・スプレモ", False, "コロンビア", None),
    ("cf10007", "グァテマラ SHB", False, "グアテマラ", None),
    ("cf10008", "タンザニア AA(キリマンジャロ)", False, "タンザニア", None),
    ("cf10010", "ニューギニア AA", False, "パプアニューギニア", None),
    ("cf10013", "ニカラグア サンチェス農園", False, "ニカラグア", "中煎り"),
    ("cf10014", "モカマタリ No.9", False, "イエメン", "中煎り"),
    ("cf10015", "ブルーマウンテン No.1", False, "ジャマイカ", "中煎り"),
    ("cf10016", "ブラジル ウォッシュト", False, "ブラジル", "中煎り"),
    ("cf10011", "マラゴジッペ", False, "コロンビア", None),
    ("cf10020", "ベトナム アラビカ種", False, "ベトナム", "浅煎り"),
    ("cf10021", "ホンジュラス", False, "ホンジュラス", "浅煎り"),
    ("cf10022", "パナマ・ドンパチ ゲイシャ", False, "パナマ", None),
    ("cf10023", "パナマ・ドンパチ 貴婦人", False, "パナマ", "浅煎り"),
]

PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
WEIGHT_PATTERN = re.compile(r"内容量[:：\s]*(\d+)\s*g")
MATERIAL_PATTERN = re.compile(r"原材料[:：]\s*([^\n]+)")


def fetch(code: str) -> requests.Response:
    resp = requests.get(ITEM_URL.format(code=code), headers=REQUEST_HEADERS, timeout=90)
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def extract_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one("span.sale_desc")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    text = text.split("私は西洋料理")[0]
    lines = [l for l in text.split("\n")
             if l and not l.startswith(("http", "--送料無料", "この商品は送料込み"))]
    return re.sub(r"\s+", " ", " ".join(lines)).strip().strip('"').strip()[:400] or None


def build_record(code, name, is_blend, origin, roast) -> dict | None:
    resp = fetch(code)
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    text = resp.text
    soup = BeautifulSoup(text, "html.parser")
    item_desc = soup.select_one("span.item_desc")
    meta = unicodedata.normalize("NFKC", item_desc.get_text("\n", strip=True)) if item_desc else ""
    weight_m = WEIGHT_PATTERN.search(meta)
    material_m = MATERIAL_PATTERN.search(meta)
    price_m = PRICE_PATTERN.search(text)
    avail_m = AVAIL_PATTERN.search(text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["origin_country"] = origin
    processing = None if is_blend else (detect_processing_method(material_m.group(1)) if material_m else None)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": extract_description(soup),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code, name, is_blend, origin, roast in ITEMS:
        try:
            record = build_record(code, name, is_blend, origin, roast)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {code} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kastnercoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kastnercoffee.json に出力しました")


if __name__ == "__main__":
    main()
