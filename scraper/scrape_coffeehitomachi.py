# -*- coding: utf-8 -*-
"""
scrape_coffeehitomachi.py

珈琲人町(長崎県長崎市東古川町4-25 プライオリティ1F、カラーミーショップ/
shop-pro.jp、ストア名「ONLINE SHOP 珈琲人町」)の商品情報を取得する。
公式サイト kasa-hitomachi.com は「笠」(珈琲と器)と「珈琲人町」(コーヒー
スタンド)の2屋号を束ねるポータルで、特定商取引法の販売業者表記は
「珈琲人町 竹下雅哉」(2026-10-18確認)。店名は「珈琲人町」とする。

【商品選別】
全17商品(?mode=srh&cid=&keyword=、2ページ)のうち、商品名が「200g」で
始まる豆7種(シングル3、人町ブレンド3、笠ブレンド1)のみ採用。
ドリップバッグ、水出しコーヒーパック、Gift Box、笠ブレンド Drip Bag
(10P/20P)は除外。豆7種は全て200g単一サイズ(豆/粉の挽き方選択は同一商品)。

【在庫】カラーミー側は在庫管理なし(inventory_control: none)で売り切れ表示
が無いため、商品名の「SOLD OUT」等のテキストのみで判定する。

robots.txt確認済み(2026-10-18): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲人町",
    "url": "https://coffeehitomachi.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "長崎県長崎市東古川町4-25 プライオリティ1F",
    "prefecture": "長崎県",
    "robots_txt_status": "許可(2026-10-18確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://coffeehitomachi.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&cid=&keyword=&page={page}"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 2

BEAN_PREFIX = re.compile(r"^\s*(\d+)\s*g\b")
EXCLUDE_KEYWORDS = ["Drip Bag", "ドリップ", "水出し", "Gift", "ギフト", "福包み", "セット"]
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
DESC_STOP = re.compile(r"\d+\s*g\s*[　 ]*[\d,]+円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        soup = fetch_page(LIST_URL.format(page=page))
        added = 0
        for box in soup.select("div.item_box"):
            a = box.select_one("p.item_name a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            added += 1
            items.append({"raw_name": clean(a.get_text()), "pid": m.group(1),
                          "product_url": f"{BASE_URL}?pid={m.group(1)}"})
        time.sleep(CRAWL_DELAY_SECONDS)
        if added == 0:
            break
    return items


def extract_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one("div.product_description")
    if not el:
        return None
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text()
    m = DESC_STOP.search(text)
    if m:
        text = text[:m.start()]
    text = "".join(l.strip() for l in text.split("\n"))
    return text.strip() or None


def extract_price_weight(soup: BeautifulSoup, name: str):
    m = re.search(r'"sales_price_including_tax":(\d+)', soup.decode())
    price = int(m.group(1)) if m else None
    w = BEAN_PREFIX.match(name)
    return price, int(w.group(1)) if w else None


def scrape_all_products():
    items = scrape_list()
    records, excluded = [], []
    for it in items:
        name = it["raw_name"]
        if not BEAN_PREFIX.match(name) or any(k in name for k in EXCLUDE_KEYWORDS):
            excluded.append({"shop_name": SHOP_INFO["name"], "raw_name": name,
                             "non_bean": True, "product_url": it["product_url"]})
            continue
        soup = fetch_page(it["product_url"])
        time.sleep(CRAWL_DELAY_SECONDS)
        price, weight = extract_price_weight(soup, name)
        parsed = parse_product(name)
        stock_status = detect_stock_status(name)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": (ROAST_PATTERN.search(name).group(1)
                            if ROAST_PATTERN.search(name) else parsed["roast_level"]),
            "flavor_notes": extract_description(soup),
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": it["product_url"],
        })
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": [],
              "non_bean_products_excluded": excluded}
    with open("data_coffeehitomachi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeehitomachi.json に出力しました"
          f"(非コーヒー豆{len(excluded)}件は別枠に分離)")
