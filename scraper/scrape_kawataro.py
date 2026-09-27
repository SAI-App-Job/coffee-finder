# -*- coding: utf-8 -*-
"""
scrape_kawataro.py

河太郎珈琲店(kawatarocoffee.com、京都府京都市左京区大原古知平町28、
自家焙煎豆のオンライン販売)の商品情報を取得する。MakeShop。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp「京都のおすすめコーヒー豆専門店
13選」)で発見。大原(鴨川上流)の自家焙煎店。

【対象カテゴリについて】
実データ確認済み(2026-09時点): shopbrand/001(ストレート4銘柄)・002/004/
005/006(ブレンド4銘柄、それぞれ独自の商品名を持つ)を対象とする。
shopbrand/003(初回限定お試しセット、複数銘柄セット)は対象外。全8銘柄が
200g/500gの2重量展開のため、最小重量(200g)側のみ採用する。

【商品説明について】
実データ確認済み: og:descriptionに短いテイスティング文のみが入っており、
産地・精製方法等の構造化情報は無い。存在しない情報を創作しないため
flavor_notesのみ採用し、他の詳細フィールドはparse_product()によるタイトル
解析に委ねる。
"""

import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "河太郎珈琲店",
    "url": "https://kawatarocoffee.com/",
    "platform": "MakeShop",
    "address": "京都府京都市左京区大原古知平町28",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(MakeShop標準構成を想定)",
}

BASE_URL = "https://kawatarocoffee.com"
CATEGORY_IDS = ["001", "002", "004", "005", "006"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"\s*\d+\s*[gｇ]\s*", re.IGNORECASE)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_pids() -> list[str]:
    pids: set[str] = set()
    for cat in CATEGORY_IDS:
        text = fetch(f"{BASE_URL}/shopbrand/{cat}/O/")
        pids |= set(re.findall(r"/shopdetail/(\d+)/", text))
    return sorted(pids)


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_WEIGHT_PATTERN.sub("", item["title"])
        base = re.sub(r"[\s　]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    parsed = apply_category_hint_fallback(parsed, title)
    stock_status = detect_stock_status(title)

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
        "flavor_notes": item["flavor_notes"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids = fetch_pids()

    prelim = []
    for pid in pids:
        url = f"{BASE_URL}/shopdetail/{pid}/"
        try:
            text = fetch(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        title_m = re.search(r'<meta property="og:title" content="([^"]*)"', text)
        if not title_m:
            continue
        title = title_m.group(1).split("-河太郎珈琲店")[0].strip()
        price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', text)
        desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', text)
        weight_m = WEIGHT_PATTERN.search(title)
        prelim.append({
            "url": url, "title": title,
            "price": int(float(price_m.group(1))) if price_m else None,
            "flavor_notes": desc_m.group(1).strip() if desc_m and desc_m.group(1).strip() else None,
            "weight_g": int(weight_m.group(1)) if weight_m else None,
        })

    deduped = dedupe_by_base_name(prelim)

    records = []
    flavored_records = []
    for item in deduped:
        detail = build_record(item)
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
    with open("data_kawataro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kawataro.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
