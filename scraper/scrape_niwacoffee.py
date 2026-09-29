# -*- coding: utf-8 -*-
"""
scrape_niwacoffee.py

NIWA COFFEE(niwacoffee.jp、群馬県館林市当郷町1933-2)の商品情報を
取得する。EC-CUBE系の自社ECサイト。

【店舗発見の経緯】
全国再調査(群馬県)でサブエージェント調査から発見。当初「公式サイトの
更新が2020年以降止まっている可能性あり」とフラグが立っていたが、
実際に確認したところ2026年9月時点の定休日カレンダー・価格改定情報が
最新化されており、現役で営業中と確認できた。

【対象商品について】
実データ確認済み(2026-09時点): category_id=3(ブレンドコーヒー、5件)・
category_id=4(ストレートコーヒー、11件)の計16件を対象とする。
category_id=18(コーヒー豆セット)・9(ドリップバッグ)・2(コーヒー器具)
は非対象として除外。

【ページ構造について】
実データ確認済み: 商品名は`<h2>`タグ、価格は`id="price02_default"`の
span要素、商品説明は`<div class="main_comment">`から取得できる。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "NIWA COFFEE",
    "url": "http://www.niwacoffee.jp/",
    "platform": "自社ECサイト(EC-CUBE系)",
    "address": "群馬県館林市当郷町1933-2",
    "prefecture": "群馬県",
    "robots_txt_status": "未確認",
}

BASE_URL = "http://www.niwacoffee.jp"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

CATEGORY_IDS = [3, 4]  # ブレンドコーヒー・ストレートコーヒー

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def list_product_ids() -> list[str]:
    ids = []
    for cid in CATEGORY_IDS:
        resp = requests.get(f"{BASE_URL}/products/list.php?category_id={cid}", headers=REQUEST_HEADERS, timeout=20)
        resp.encoding = resp.apparent_encoding
        found = re.findall(r"product_id=(\d+)", resp.text)
        for pid in found:
            if pid not in ids:
                ids.append(pid)
    return ids


def build_record(product_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/products/detail.php?product_id={product_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    h2 = soup.select_one("#detailrightbloc h2")
    if not h2:
        return None
    title = h2.get_text(strip=True)

    price_span = soup.select_one("#price02_default")
    price = int(re.sub(r"[^\d]", "", price_span.get_text())) if price_span else None

    comment_div = soup.select_one("div.main_comment")
    desc = comment_div.get_text(" ", strip=True)[:500] if comment_div else None

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    parsed = parse_product(title)
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title) or (detect_country_name(desc) if desc else None)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
        parsed = apply_category_hint_fallback(parsed, desc or "")

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
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{BASE_URL}/products/detail.php?product_id={product_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for product_id in list_product_ids():
        try:
            detail = build_record(product_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: product_id={product_id} ({e})")
            continue
        if detail is None:
            continue
        records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_niwacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_niwacoffee.json に出力しました")


if __name__ == "__main__":
    main()
