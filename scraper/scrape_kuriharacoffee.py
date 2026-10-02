# -*- coding: utf-8 -*-
"""
scrape_kuriharacoffee.py

KURIHARA COFFEE ROASTERS(store.kurihara-coffee.jp、埼玉県さいたま市桜区
下大久保、2019年開業。2026年5月に東京都北区岩淵町へ赤羽店を開店し計2店舗、
チェーン基準には該当しない)の商品情報を取得する。BASE。オーナーはQグレーダー、
自家焙煎(HB-L2・SR5)。

【対象商品について】
実データ確認済み(2026-10時点): 全16商品のうち、ディップスタイルコーヒー・
SIMPLIFY the Brewer(器具)を除いた豆商品を対象とする。同一銘柄が
重量違い(100g/250g/500g/1kg)で個別商品ページとして登録されているため、
他店舗と同様に最小の代表重量(100g。Cup of Excellenceのみ50g)の商品のみを
収録し、重量違いの重複は除外している。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、
User-agent: *では許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "KURIHARA COFFEE ROASTERS",
    "url": "https://store.kurihara-coffee.jp/",
    "platform": "BASE",
    "address": "埼玉県さいたま市桜区下大久保",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://store.kurihara-coffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 重量違い(250g/500g/1kg)の重複・ディップ・器具は除外済み
ITEM_IDS = [
    "149527986",  # Cup of Excellence Brazil 2025 #1 (50g)
    "83683820",   # KURIHARA BLEND 100g
    "83684422",   # ESPRESSO BLEND 100g
    "157574321",  # CHINA DEHONG 100g
    "83684174",   # Ethiopia Silinga Natural 100g
    "83684336",   # Tanzania Azania Tamu Washed 100g
]

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"【\s*焙煎度\s*】\s*([^【\s]+)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).split(" | ")[0]).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1).strip() if desc_m else None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    roast_m = ROAST_PATTERN.search(desc or "")
    roast_level = roast_m.group(1) if roast_m else None

    parsed = parse_product(title)
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        if not parsed["origin_country"] and "china" in title.lower():
            parsed["origin_country"] = "中国"
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is not None:
            records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kuriharacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kuriharacoffee.json に出力しました")


if __name__ == "__main__":
    main()
