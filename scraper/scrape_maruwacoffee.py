# -*- coding: utf-8 -*-
"""
scrape_maruwacoffee.py

マルワコーヒー(maruwa.raku-uru.jp、埼玉県上尾市上1135-1、1972年創業、独自の焙煎機で
自家焙煎)の商品情報を取得する。ラクウル(raku-uru.jp)。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「ストレート豆(100g焙煎豆)」(categoryId=12643)・
「ブレンド豆(100g焙煎豆)」(categoryId=12641)の2カテゴリを対象とする。
コーヒーギフト・前受金(チャージ)・ONE DRIP(ドリップバッグ)・紅茶は除外。
カテゴリ名のとおり全て100g。在庫数が0の商品(「バリアラビカ神山」は入荷困難の
ため焙煎を控えている)は完売として収録する。

【ページ構造について】
実データ確認済み: 商品名は`<h1 class="title1">`、価格は「販売価格 / 648円」、
在庫は「在庫 / 0」、説明は「商品詳細」直後の行。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "マルワコーヒー",
    "url": "https://maruwa.raku-uru.jp/",
    "platform": "ラクウル(raku-uru.jp)",
    "address": "埼玉県上尾市上1135-1",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://maruwa.raku-uru.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = {"12643": "ストレート", "12641": "ブレンド"}
# 水出しパックは豆ではなくパック製品、会員様専用カートは一般販売外のため除外
EXCLUDE_KEYWORDS = ("水出しコーヒーパック", "会員様専用")


def list_items() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for category_id, kind in CATEGORY_IDS.items():
        resp = requests.get(f"{BASE_URL}/item-list?categoryId={category_id}", headers=REQUEST_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        for item_id in re.findall(r"/item-detail/(\d+)", resp.text):
            if all(item_id != existing for existing, _ in items):
                items.append((item_id, kind))
    return items


def build_record(item_id: str, kind: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/item-detail/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    h1 = soup.select_one("h1.title1")
    if not h1:
        return None
    name = re.sub(r"\s+", " ", h1.get_text(strip=True))
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None

    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    def after(label: str) -> str | None:
        for i, ln in enumerate(lines):
            if ln == label and i + 1 < len(lines):
                return lines[i + 1]
        return None

    price_text = after("販売価格") or ""
    price_m = re.search(r"([\d,]+)\s*円", price_text)
    stock_text = after("在庫") or ""
    out_of_stock = stock_text.isdigit() and int(stock_text) == 0
    desc = after("商品詳細")

    parsed = parse_product(name)
    if kind == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and "バリ" in name:
            parsed["origin_country"] = "インドネシア"
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
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "weight_g": 100,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": f"{BASE_URL}/item-detail/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, kind in list_items():
        try:
            record = build_record(item_id, kind)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_maruwacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_maruwacoffee.json に出力しました")


if __name__ == "__main__":
    main()
