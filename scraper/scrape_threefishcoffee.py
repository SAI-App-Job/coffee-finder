# -*- coding: utf-8 -*-
"""
scrape_threefishcoffee.py

THREE FISH COFFEE ROASTERS(https://threefishcoffee.shop-pro.jp/、愛媛県松山市福音寺町260-3)の商品情報を取得する。カラーミーショップ(EUC-JP)。

【店舗発見の経緯】
全国再調査(愛媛県)で対象とした。現行ストアはカラーミー(threefishcoffee.shop-pro.jp)。

【対象商品について】
実データ確認済み(2026-10時点): 全43商品のうち、ドリップパック・ギフト・器具・菓子を除く豆を対象とする。同一銘柄が100g/200gで別ページ登録されているため100gを代表とし、100gが無い2銘柄(コロンビア・スウィートベリーSUP、タンザニアAA・スノートップ)のみ200gを採用した。旧BASE店は使わない。
対象商品のID・表示名・重量・分類・焙煎度・産地は下のITEMSに明示している。
価格・在庫・説明文は商品ページ(var Colorme のJSONと本文)から取得する。

【在庫について】
var Colorme のstock_numが0以下、または「カートに入れる」ボタンが存在しない商品を品切れとする。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10確認)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "THREE FISH COFFEE ROASTERS",
    "url": "https://threefishcoffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛媛県松山市福音寺町260-3",
    "prefecture": "愛媛県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://threefishcoffee.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 表示名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動判定))
ITEMS = [('191816390', 'デカフェ(DE CAF)ペルー カハマルカ ハエン地区有機豆', 100, None, None, 'ペルー'),
 ('190447485', 'デカフェ(DE CAF)ホンジュラスHG有機豆', 100, None, None, 'ホンジュラス'),
 ('165687582', 'スリーフィッシュブレンド(ペルー・コロンビア・エチオピア)', 100, 'ブレンド', None, None),
 ('165700589', 'エスプレッソブレンド(インドネシア・ブラジル・他)', 100, 'ブレンド', None, None),
 ('165700608', 'ストロングブレンドTFC(インドネシア・ブラジル)', 100, 'ブレンド', None, None),
 ('165696344', 'ジャマイカ ブルーマウンテン N0,1', 100, None, None, 'ジャマイカ'),
 ('165700615', 'インドネシア・マンデリン・ビンタンリマ', 100, None, None, 'インドネシア'),
 ('167473403', 'ペルー・マチュピチュ(Qグレード)', 100, None, None, 'ペルー'),
 ('167539663', 'パプアニューギニア・AX・タイガットスペシャル', 100, None, None, 'パプアニューギニア'),
 ('167539772', 'エチオピア イルガチェフェ GELSI ウォッシュ', 100, None, None, 'エチオピア'),
 ('171913889', 'ブラジル クイーンショコラ', 100, None, None, 'ブラジル'),
 ('171914901', 'グアテマラ カフェ ピューマ', 100, None, None, 'グアテマラ'),
 ('179407949', 'ミャンマー ユワンガン州 G1 ナチュラル', 100, None, None, 'ミャンマー'),
 ('180101931', 'エチオピア ゲイシャ種 ジャスミン G1', 100, None, None, 'エチオピア'),
 ('165700623', 'イエメン・ガーリブ・ゴールド', 100, None, None, 'イエメン'),
 ('189877348', 'コロンビア・スウィートベリーSUP', 200, None, None, 'コロンビア'),
 ('189877139', 'タンザニアAA・スノートップ(キリマンジャロ)', 200, None, None, 'タンザニア')]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)


def fetch_page(pid: str):
    resp = requests.get(f"{BASE_URL}?pid={pid}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    soup = BeautifulSoup(resp.text, "html.parser")
    m = COLORME_JSON_PATTERN.search(resp.text)
    product = json.loads(m.group(1)).get("product", {}) if m else {}
    return soup, product


def pick_price(product: dict, weight_g: int) -> int | None:
    pat = re.compile(rf"(?<!\d){weight_g}g")
    for v in product.get("variants", []):
        text = unicodedata.normalize("NFKC", f"{v.get('option1_value') or ''} {v.get('option2_value') or ''}")
        if pat.search(text):
            return v.get("option_price_including_tax")
    return product.get("sales_price_including_tax")


def is_sold_out(soup: BeautifulSoup, product: dict) -> bool:
    stock = product.get("stock_num")
    if isinstance(stock, int) and stock <= 0:
        return True
    return "カートに入れる" not in soup.get_text(" ", strip=True)


def extract_desc_and_roast(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    el = soup.select_one("[class*=expl]")
    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""
    roast_m = re.search(r"焙煎度合\s*(\S+)", text)
    roast = roast_m.group(1) if roast_m else None
    text = text.replace("商品説明", "")
    text = re.sub(r"\d+[gｇ]以上送料無料!*", "", text)
    text = re.split(r"酸味\s*★", text)[0].strip()
    return (text[:400] or None), roast



def build_record(item) -> dict | None:
    pid, name, weight_g, category_override, roast_level, origin_override = item
    soup, product = fetch_page(pid)
    desc, page_roast = extract_desc_and_roast(soup)
    sold_out = is_sold_out(soup, product)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin_override:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "description"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or page_roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": pick_price(product, weight_g),
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_threefishcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_threefishcoffee.json に出力しました")


if __name__ == "__main__":
    main()
