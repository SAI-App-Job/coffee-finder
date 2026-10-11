# -*- coding: utf-8 -*-
"""
scrape_aromacoffeeroastery.py

アロマコーヒーロースタリー(aroma-coffee.jp、岡山県岡山市北区下中野351-115、
スペシャルティコーヒー専門店の自家焙煎豆オンライン販売)の商品情報を取得する。
ショップサーブ(ShopServe、UTF-8)。

【対象商品について】
実データ確認済み(2026-10時点): 商品カテゴリ「250gセット割引対象パック」
(/SHOP/1089549/list.html、2ページ構成、全11件)のうち、水出しアイスコーヒー(6バッグ)を
除く10件(ストレート7・ブレンド3)の250g商品を収録する。
そのほかのカテゴリ(初回限定飲み比べセット、150g2袋セット、お得用1.5kgパック、
定期便、ギフト、コーヒーバッグ、器具、水出し、カフェ・オ・レベース)は対象外。
商品名は「ラ・アスンシオン【深煎り】 250g」の形式で、焙煎度は【】内、重量は末尾の「250g」。
価格は税込。在庫は詳細ページの「豆の挽き方 / 在庫」表(在庫あり/在庫なし表記)から判定する。
産地は詳細ページの「生産国」行、風味は「風味特性」行から取る。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "アロマコーヒーロースタリー",
    "url": "https://aroma-coffee.jp/",
    "platform": "ショップサーブ",
    "address": "岡山県岡山市北区下中野351-115",
    "prefecture": "岡山県",
    "robots_txt_status": "未確認(robots.txtは404)",
}

BASE_URL = "https://aroma-coffee.jp"
LIST_URL = f"{BASE_URL}/SHOP/1089549/list.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップ", "バッグ", "定期便", "水出し", "ベース", "器具")
MAX_PAGES = 10

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"【([^】]*煎り)(?:ブレンド)?】")
COUNTRY_PATTERN = re.compile(r"生産国\s*/+\s*([^\s\n]+)")
FLAVOR_PATTERN = re.compile(r"風味特性\s*[：:]\s*([^\n]+)")
PRICE_PATTERN = re.compile(r"[¥￥]\s*([\d,]+)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else LIST_URL.replace("list.html", f"list{page}.html")
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for card in soup.select("section.column4"):
            a = card.select_one("h2 a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            price_el = card.select_one(".selling_price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            items.append({
                "title": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "path": href,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
            })
        if new == 0:
            break
        time.sleep(0.5)
    return items


def fetch_detail(path: str) -> dict:
    soup = BeautifulSoup(fetch(BASE_URL + path), "html.parser")
    text = soup.get_text("\n", strip=True)
    # 「豆の挽き方 / 在庫」表: 各行の直後に「在庫あり」「在庫なし」等が並ぶ
    stock_words = re.findall(r"(在庫あり|在庫なし|在庫切れ|売り切れ|売切れ|品切れ|入荷待ち)", text.split("関連商品")[0])
    in_stock = any(w == "在庫あり" for w in stock_words)
    country_m = COUNTRY_PATTERN.search(text)
    flavor_m = FLAVOR_PATTERN.search(text)
    return {
        "in_stock": in_stock if stock_words else True,
        "country": country_m.group(1).strip() if country_m else None,
        "flavor": flavor_m.group(1).strip() if flavor_m else None,
    }


def build_record(item: dict, detail: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", title)
    weight_m = WEIGHT_PATTERN.search(norm)
    weight_g = int(weight_m.group(1)) if weight_m else None
    roast_m = ROAST_PATTERN.search(norm)
    roast = roast_m.group(1) if roast_m else None

    name = re.sub(r"\s*\d+\s*g\s*$", "", norm)
    name = re.sub(r"\s+", " ", name).strip()

    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        country = detail["country"]
        if country and not parsed["origin_country"]:
            parsed["origin_country"] = country
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            d = detect_country_name(name)
            if d:
                parsed["origin_country"] = d
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    in_stock = detail["in_stock"]
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
        "roast_hint": None,
        "flavor_notes": detail["flavor"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["title"] for kw in EXCLUDE_KEYWORDS):
            continue
        detail = fetch_detail(item["path"])
        time.sleep(0.5)
        record = build_record(item, detail)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_aromacoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_aromacoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
