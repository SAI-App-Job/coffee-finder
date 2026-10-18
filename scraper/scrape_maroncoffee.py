# -*- coding: utf-8 -*-
"""
scrape_maroncoffee.py

おうちカフェ マロン(マロンコーヒーshop、maron.raku-uru.jp、長崎県雲仙市
小浜町北野1247-1、販売事業者「おうちカフェマロン 隈部由紀子」、楽売/
Raku-Uru)の商品情報を取得する。scrape_sabucoffee.py と同一プラットフォーム。

【住所】特定商取引法ページ(https://maron.raku-uru.jp/law)で
「〒854-0515 長崎県雲仙市小浜町北野1247-1」を確認(2026-10-18)。

robots.txt: /robots.txt は404相当のHTML(トップページ)が返り、制限記述は
存在しない(2026-10-18確認)。一覧・詳細ページのみ取得する。

【商品選別】
/item-list の全9商品のうち:
- 「贅沢‼スペシャルブレンド 100g」(item-detail/1894408): 採用(ブレンド)。
- 「選べるコーヒー豆100gお試しサイズ」(item-detail/1894889): 1ページに
  ブラジル(中煎り)・グアテマラ(中煎り)・コロンビア(深煎り)の3銘柄が
  選択肢として載っている(全て100g・875円)ため、銘柄ごとに1件ずつ展開して
  採用。product_url は ページURL#銘柄名 で一意化。
- 除外: ロボ友ひみつのコーヒー(オリジナル印刷ドリップコーヒー)、
  マロンのドリップパック、一杯のきもち(同・大容量)、二週間セット、
  世界のコーヒー飲み比べセット、ワールドコーヒー体験セット(いずれも
  ドリップバッグ/セット/詰め合わせ)。

【在庫】香月庵・サブ珈琲と同じ構造フラグ(div.item-dtail-orderinvalid が
あり a.raku-add-cart が無い場合に品切れ)で判定する。選択肢ごとの在庫は
表示されない(ページ全体の在庫数のみ)ため、3銘柄は共通の判定とする。
"""

import json
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "おうちカフェ マロン",
    "url": "https://maron.raku-uru.jp/",
    "platform": "楽売(Raku-Uru)",
    "address": "長崎県雲仙市小浜町北野1247-1",
    "prefecture": "長崎県",
    "robots_txt_status": "実質許可(2026-10-18確認。robots.txtに制限記述なし)",
}

BASE_URL = "https://maron.raku-uru.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 2

BLEND_ITEM_ID = "1894408"      # スペシャルブレンド
SELECTABLE_ITEM_ID = "1894889"  # 選べるコーヒー豆100gお試しサイズ
NON_BEAN_KEYWORDS = ["ドリップ", "セット", "ロボ友"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_LINES = ("浅煎り", "中浅煎り", "中煎り", "中深煎り", "深煎り")
SELECTABLE_COUNTRIES = ("ブラジル", "グアテマラ", "コロンビア")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_list() -> list[tuple[str, str]]:
    soup = fetch_page(f"{BASE_URL}/item-list")
    items = []
    for a in soup.select('p.item-name a[href^="/item-detail/"]'):
        item_id = a["href"].rsplit("/", 1)[-1]
        if item_id not in [i for i, _ in items]:
            items.append((item_id, a.get_text(strip=True)))
    return items


def page_price_stock(soup: BeautifulSoup):
    price_el = soup.select_one("b.raku-item-vari-price-num")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))
    orderinvalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    add_cart = soup.select_one("a.raku-add-cart") is not None
    return price, (orderinvalid and not add_cart)


def base_record(name, price, weight, url, structural_oos, notes, roast=None):
    parsed = parse_product(name)
    stock_status = detect_stock_status(name, structural_oos)
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
        "flavor_notes": notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def blend_record(item_id: str, list_name: str) -> dict:
    url = f"{BASE_URL}/item-detail/{item_id}"
    soup = fetch_page(url)
    price, oos = page_price_stock(soup)
    spec = soup.select_one("div.item-detail-spec")
    txt1 = soup.select_one("div.item-detail-txt1")
    weight = None
    m = WEIGHT_PATTERN.search(list_name)
    if m:
        weight = int(m.group(1))
    notes = None
    if txt1:
        for ln in txt1.get_text("\n", strip=True).split("\n"):
            if "ブレンドは" in ln:
                notes = ln.strip()
    # 商品名は一覧上「贅沢‼スペシャルブレンド 100g ☆」。装飾・重量を除いた
    # 店舗の呼称「スペシャルブレンド」を採用する(詳細ページ本文も同名)。
    name = "スペシャルブレンド"
    return base_record(name, price, weight, url, oos, notes)


def selectable_records(item_id: str) -> list[dict]:
    url = f"{BASE_URL}/item-detail/{item_id}"
    soup = fetch_page(url)
    price, oos = page_price_stock(soup)
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n")]
    records = []
    for i, line in enumerate(lines):
        if not line.startswith("☕"):
            continue
        name = line.lstrip("☕").strip()
        name = re.sub(r"[（(]SAC評価[^）)]*[）)]", "", name)
        name = re.sub(r"\s+", " ", name.replace("　", " ")).strip()
        roast = lines[i - 1] if i > 0 and lines[i - 1] in ROAST_LINES else None
        notes = None
        if i + 1 < len(lines) and lines[i + 1].startswith("【"):
            notes = lines[i + 1].strip("【】") or None
        rec = base_record(name, price, 100, f"{url}#{urllib.parse.quote(name)}", oos, notes, roast)
        # 「エクストラ」はコロンビア公式サブグレード(エクセルソ/スプレモ)の
        # 明記が無いため、パーサの推定グレードは採用しない
        if rec["grade"] == "エクセルソ エクストラ":
            rec["grade"] = None
        if not rec["origin_country"]:
            for c in SELECTABLE_COUNTRIES:
                if name.startswith(c):
                    rec["origin_country"], rec["origin_source"] = c, "商品名"
        records.append(rec)
    return records


def scrape_all_products():
    records, excluded = [], []
    for item_id, list_name in fetch_item_list():
        if item_id == SELECTABLE_ITEM_ID:
            records.extend(selectable_records(item_id))
        elif item_id == BLEND_ITEM_ID:
            records.append(blend_record(item_id, list_name))
        else:
            excluded.append({"shop_name": SHOP_INFO["name"], "raw_name": list_name,
                             "non_bean": True,
                             "product_url": f"{BASE_URL}/item-detail/{item_id}"})
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": [],
              "non_bean_products_excluded": excluded}
    with open("data_maroncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_maroncoffee.json に出力しました"
          f"(ドリップ/セット等{len(excluded)}件は別枠に分離)")
