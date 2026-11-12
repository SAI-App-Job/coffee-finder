# -*- coding: utf-8 -*-
"""
scrape_rodan.py

手焼珈琲RODAN(https://www.rodan24.com/、愛媛県伊予市米湊1140-4 が伊予店・焙煎所、
松山市柳井町1-13-15-1F に rodan-caffe 柳井町店)の商品情報を取得する。カラーミーショップ(独自ドメイン、EUC-JP)。

【店舗の根拠】
公式「実店舗のご案内」(https://www.rodan24.com/?mode=f2)に「1991年。愛媛/伊予に手焼珈琲RODANオープン」
「現在も手作り10キロ釜で焙煎中」「手焼珈琲RODAN 伊予店 愛媛県伊予市米湊1140-4」。
特商法表記(?mode=sk)の住所も愛媛県伊予市米湊1140-4。

【対象商品について】
実データ確認済み(2026-11-03): コーヒー豆グループ(gid=3191132)のうち、100g袋の豆(フレンチブレンド、
ソフトブレンド、N・ミックス、イエメン・モカ/フルーツショコラータ、モカブレンド、コスタリカ タラス)を対象とする。
同一銘柄の200g・500g袋、はじめてセット、ドリップバッグ、水出しバッグ、器具、カップは除外。
バリエーション「豆のまま/挽く」は豆のままの価格(同額)。

【在庫について】
var Colorme のstock_numが0以下、または「カートに入れる」ボタンが存在しない商品を品切れとする。

【robots.txtについて】
User-agent: * は /cart/ のみ制限(2026-11-03確認)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "手焼珈琲RODAN",
    "url": "https://www.rodan24.com/",
    "platform": "カラーミーショップ",
    "address": "愛媛県伊予市米湊1140-4",
    "prefecture": "愛媛県",
    "robots_txt_status": "許可(2026-11-03確認。User-agent: * は /cart/ のみ制限)",
    "source_note": "公式カラーミーショップ(https://www.rodan24.com/)のコーヒー豆グループの商品ページを2026-11-03に確認。"
                   "「実店舗のご案内」に『現在も手作り10キロ釜で焙煎中』、特商法表記の住所は伊予市米湊1140-4。"
                   "100g袋の豆のまま価格を採用し、200g/500g袋・はじめてセット・ドリップバッグ・水出しバッグ・器具は除外。"
                   "11/1にNEWS更新あり。",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://www.rodan24.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 表示名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動判定))
ITEMS = [
    ('192391711', 'フレンチブレンド100g袋', 100, 'ブレンド', '深煎り', None),
    ('192391880', 'ソフトブレンド100g袋', 100, 'ブレンド', None, None),
    ('192392065', 'N・ミックス100g袋', 100, 'ブレンド', None, None),
    ('192392272', 'イエメン・モカ/フルーツショコラータ100g袋', 100, None, None, 'イエメン'),
    ('192392375', 'モカブレンド/イエメン×フレンチ100g袋', 100, 'ブレンド', None, None),
    ('193586129', 'コスタリカ タラス アナエロビックハニー100g袋', 100, None, None, 'コスタリカ'),
]

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
    text = re.sub(r"^DETAIL\s*-*", "", text).strip()
    text = text.split("＜内容＞")[0].strip()
    return (text[:400] or None), None


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
        "roast_level": None if name.startswith("モカブレンド") else (roast_level or page_roast or parsed["roast_level"]),  # モカブレンドの「フレンチ」はブレンド構成要素で焙煎度ではない
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
    with open("data_rodan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rodan.json に出力しました")


if __name__ == "__main__":
    main()
