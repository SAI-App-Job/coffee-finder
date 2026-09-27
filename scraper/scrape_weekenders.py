# -*- coding: utf-8 -*-
"""
scrape_weekenders.py

WEEKENDERS COFFEE(weekenderscoffee.com、京都府京都市左京区田中下柳町
[出町柳]・中京区[富小路]、自家焙煎豆のオンライン販売)の商品情報を取得
する。ShopServe(さくらインターネット系カート、weekenderscoffee.com配下
に/SHOP/としてリバースプロキシされている)。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp等)で発見。2005年創業、京都の
スペシャルティコーヒーシーンを牽引する著名ロースター。

【対象商品について】
実データ確認済み(/SHOP/25341/list.html、list2.html、list3.html の
3ページで全30件、2026-09時点): ドリップバッグ各種(7件)・3 Roasters Set
(複数銘柄セット)・アイスコーヒーバッグ各種(3件)はNON_BEAN_KEYWORDSで
除外。残り19件(ストレート17・ブレンド2)を収録。

【商品説明・価格・在庫の構造について】
実データ確認済み: meta og:title/descriptionが存在しないため本文テキストを
直接解析する。ページ本文の「HOME > コーヒー豆 > ストレート(またはブレンド)」
パンくずの直後に商品名が再掲され、そこから「拡大表示」という文言が現れる
までがテイスティング文(短い風味タグのみの商品と長い文章の商品が混在)。
価格は「価格: X円 (税込)」形式。在庫は「在庫 ○」(あり)「在庫 ×」(切れ)
で判定する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "WEEKENDERS COFFEE",
    "url": "https://www.weekenderscoffee.com/",
    "platform": "ShopServe",
    "address": "京都府京都市左京区田中下柳町6-3",
    "prefecture": "京都府",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.weekenderscoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

HANDLES = [
    "COL-Jes", "COS", "ELSAL", "ETH-Che", "ETH-Gog", "KEN-Ngu", "PANAMA", "Typica",
    "BRA", "ETH-N", "GUA-Ang", "Geisha", "PERU", "ESP", "GUA", "HON", "OPE", "RWA",
]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch(handle: str) -> list[str]:
    resp = requests.get(f"{BASE_URL}/SHOP/{handle}.html", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [l.strip() for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]


def parse_content(lines: list[str]) -> tuple[str, str | None, int | None, str]:
    cat_indices = [i for i, l in enumerate(lines) if l in ("ストレート", "ブレンド")]
    cat_idx = cat_indices[-1] if cat_indices else None
    title = lines[cat_idx + 1] if cat_idx is not None else lines[0]
    end_idx = next((i for i in range(cat_idx + 2, len(lines)) if lines[i] == "拡大表示"), len(lines)) \
        if cat_idx is not None else len(lines)
    flavor_lines = lines[cat_idx + 2:end_idx] if cat_idx is not None else []
    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None

    price = None
    price_idx = next((i for i, l in enumerate(lines) if l == "価格:"), None)
    if price_idx is not None:
        m = PRICE_PATTERN.search(lines[price_idx + 1])
        if m:
            price = int(m.group(1).replace(",", ""))

    stock_idx = next((i for i, l in enumerate(lines) if l == "在庫"), None)
    in_stock = lines[stock_idx + 1] == "○" if stock_idx is not None and stock_idx + 1 < len(lines) else True

    return title, flavor_notes, price, ("販売中" if in_stock else "一時的に品切れ")


def build_record(handle: str) -> dict | None:
    lines = fetch(handle)
    title, flavor_notes, price, stock_status_override = parse_content(lines)

    parsed = parse_product(title)
    url = f"{BASE_URL}/SHOP/{handle}.html"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    parsed = apply_category_hint_fallback(parsed, title)
    weight_m = WEIGHT_PATTERN.search(title)
    stock_status = detect_stock_status(title)
    if stock_status == "販売中":
        stock_status = stock_status_override

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for handle in HANDLES:
        try:
            detail = build_record(handle)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {handle} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_weekenders.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_weekenders.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
