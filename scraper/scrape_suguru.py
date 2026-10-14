# -*- coding: utf-8 -*-
"""
scrape_suguru.py

逸珈琲(スグルコーヒー、suguru-coffee.jp、香川県高松市林町1545-1)の商品情報を取得する。
xaas3.jp系ASPカート(独自ドメイン)。

【住所について】
実データ確認済み(2026-10-15): 店舗案内(/shop.html、席数60席・営業時間7:00-17:00のカフェ)の
所在地は「高松市林町1545-1」、特定商取引法表記(/info.html)の所在地は販売業者「有限会社
エス・オー企画」の「高松市林町1563-2」で食い違う。店舗案内の住所=来店できる店舗なので
こちらを採用する(特商法側は法人の所在地とみられるが、公式に明記はない)。

【対象商品】
実データ確認済み: 「コーヒー豆一覧」(/beans.html)の12銘柄がそれぞれ1カテゴリ(/category/9〜20/)を
持ち、各カテゴリに100g・500g【20%OFF】・1kg【30%OFF】の3商品が並ぶ。代表は100g(800円等)。
500g・1kgは同一銘柄の大容量違いなので除外。生産国・農園情報は詳細ページ「生豆生産国」「生産処理」から取る。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (apply_category_hint_fallback, detect_stock_status,
                           normalize_processing_method, parse_product)

SHOP_INFO = {
    "name": "逸珈琲",
    "url": "https://www.suguru-coffee.jp/",
    "platform": "独自カート(xaas3.jp)",
    "address": "香川県高松市林町1545-1",
    "prefecture": "香川県",
    "robots_txt_status": "許可(2026-10確認。User-Agent: * で/default/error/と/preview/のみDisallow)",
}

BASE_URL = "https://www.suguru-coffee.jp"
CATEGORY_IDS = range(9, 21)
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\b")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def detail(url: str) -> dict:
    soup = fetch(url)
    box = soup.select_one("#itemDetail01")
    price_el = box.select_one("li.sales_price span.data")
    price_m = re.search(r"([\d,]+)円", price_el.get_text()) if price_el else None
    stock_el = box.select_one("li.stock1 p.data")
    stock_txt = stock_el.get_text(strip=True) if stock_el else ""
    spec_text = box.get_text("\n", strip=True)
    origin = re.search(r"生豆生産国\n([^\n]+)", spec_text)
    process = re.search(r"生産処理[：:]\s*([^\n]+)", spec_text)
    farm_lines = [ln for ln in spec_text.split("\n")
                  if re.match(r"(生産国|農園名|農園主|地域|標高|品種|生産処理)\s*[：:]", ln)]
    return {
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "out_of_stock": "在庫切れ" in stock_txt,
        "origin": origin.group(1).strip() if origin else None,
        "process": process.group(1).strip() if process else None,
        "farm_note": " / ".join(re.sub(r"\s+", "", ln) for ln in farm_lines) or None,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records, excluded = [], []
    for cid in CATEGORY_IDS:
        soup = fetch(f"{BASE_URL}/category/{cid}/")
        time.sleep(CRAWL_DELAY_SECONDS)
        cands = []
        for li in soup.select("ul.itemList > li"):
            a = li.select_one("p.name a")
            if not a:
                continue
            title = a.get_text(strip=True)
            m = WEIGHT_PATTERN.search(title.replace("kg", "000g"))
            cands.append((int(m.group(1)) if m else 10**9, title, a["href"]))
        cands.sort()
        for idx, (w, title, href) in enumerate(cands):
            if idx > 0:
                excluded.append({"raw_name": title, "product_url": href, "reason": "同一銘柄の大容量違い(最小重量を代表に)"})
        w, title, href = cands[0]
        d = detail(href)
        time.sleep(CRAWL_DELAY_SECONDS)
        name = re.sub(r"\s*\d+\s*(g|kg)\s*(【[^】]*】)?\s*$", "", title).strip()
        parsed = parse_product(name)
        if d["origin"] and not parsed["origin_country"]:
            parsed["origin_country"] = d["origin"]
            parsed["origin_source"] = "detail_page"
        parsed = apply_category_hint_fallback(parsed, None)
        if d["process"] and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(d["process"])
        stock_status = detect_stock_status(title, d["out_of_stock"])
        records.append({
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
            "flavor_notes": None,
            "farm_note": d["farm_note"],
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": d["price"],
            "weight_g": w if w < 10**9 else None,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": href,
        })
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    with open("data_suguru.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records, "excluded_variants": excluded},
                  f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_suguru.json に出力しました(大容量違い{len(excluded)}件を除外)")
