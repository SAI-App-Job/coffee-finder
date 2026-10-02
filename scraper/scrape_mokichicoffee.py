# -*- coding: utf-8 -*-
"""
scrape_mokichicoffee.py

MOKICHI珈琲(mokichi-coffee.com、千葉県松戸市日暮1-2-8 雅裕ビル1F、新八柱駅徒歩2分、
スペシャルティコーヒー豆専門店。「当店で焙煎したコーヒー」と明記された自家焙煎店)の
商品情報を取得する。ショップサーブ(ShopServe、UTF-8)。

【店舗発見の経緯】
千葉県の自家焙煎店調査(ショップサーブ系)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「コーヒー豆」カテゴリ(/SHOP/47799/list.html、
全13件・10件ずつ2ページで、2ページ目はlist2.html)のうち、複数銘柄のランダム詰め合わせ
「おまかせコーヒー400g (200g x 2袋)」を除く12件(ブレンド4・ストレート8)を収録する。
別カテゴリのリキッドタイプコーヒー(ひいやりアイスリキッド)・ギフトは対象外。
各銘柄は単一サイズ(200g、ゲイシャのみ「100g単位での販売」)で、重量は商品名の
末尾「200g」「100g」から取る。価格は税込。
在庫は一覧ページの商品画像欄に出る「在庫切れ」の有無で判定する
(2026-10時点で朝のブレンド・グァテマラが在庫切れ)。
商品名の末尾の重量表記を除いたものをraw_nameとし、詳細ページの
「地域:…品種:…標高:…精製」行をfarm_note、一覧の説明文をflavor_notesとする。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "MOKICHI珈琲",
    "url": "https://mokichi-coffee.com/",
    "platform": "ショップサーブ",
    "address": "千葉県松戸市日暮1-2-8 雅裕ビル1F",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://mokichi-coffee.com"
CATEGORY_PATH = "/SHOP/47799"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("おまかせ", "セット", "ギフト", "ドリップ", "リキッド", "アイスリキッド")
MAX_PAGES = 10

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\s*$", re.IGNORECASE)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        suffix = "list.html" if page == 1 else f"list{page}.html"
        soup = BeautifulSoup(fetch(f"{BASE_URL}{CATEGORY_PATH}/{suffix}"), "html.parser")
        cards = soup.select("div.layout1")
        new = 0
        for card in cards:
            a = card.select_one("h2.goods a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            price_el = card.select_one("div.price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            expl = card.select_one("div.expl")
            items.append({
                "title": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "path": href,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "desc": re.sub(r"\s+", " ", expl.get_text(" ", strip=True)).strip() if expl else None,
                "sold_out": "在庫切れ" in card.get_text(),
            })
        if new == 0:
            break
    return items


def fetch_farm_note(path: str) -> str | None:
    try:
        text = BeautifulSoup(fetch(f"{BASE_URL}{path}"), "html.parser").get_text("\n", strip=True)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {path} ({e})")
        return None
    for ln in text.split("\n"):
        if ln.startswith("地域：") or ln.startswith("地域:"):
            return re.sub(r"\s+", " ", ln).strip()
    return None


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    weight_m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", title))
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*\d+\s*[gｇ]\s*$", "", title).strip()
    name = re.sub(r"[\s　]+", " ", name)

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": item["desc"],
        "farm_note": fetch_farm_note(item["path"]),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        record = build_record(item)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mokichicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mokichicoffee.json に出力しました")


if __name__ == "__main__":
    main()
