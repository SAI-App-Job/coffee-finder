# -*- coding: utf-8 -*-
"""
scrape_polecafe.py

ぽれ珈琲(pole-cafe.com)の自家焙煎コーヒー豆の商品情報を取得する。栃木県足利市。
WordPress + Welcart(/usces-cart/)。商品はカテゴリ「自家焙煎珈琲豆」(category/item/roasted/)
の投稿(ページ送りあり、約23件)で、各投稿に価格(div.field_price)、在庫状態、
「製法」「焙煎度合」「地域」「品種」の定型行、重量別の価格選択肢(100g〜1kg)がある。
2026-10-12確認。robots.txtは /renewal/wp-admin/ のみ除外。
代表価格は最小重量(100g)の選択肢。ドリップパックは除外する。
"""
import re
import time
import json

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "ぽれ珈琲",
    "url": "https://pole-cafe.com/",
    "platform": "WordPress + Welcart",
    "address": "栃木県足利市葉鹿町1239-3",
    "prefecture": "栃木県",
    "robots_txt_status": "許可(2026-10-12確認。/renewal/wp-admin/以外は制限なし)",
}
CRAWL_DELAY_SECONDS = 1
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LIST_URL = "https://pole-cafe.com/category/item/roasted/"
# ジャクーバードは20g単位販売で価格の基準重量が不明のため除外
EXCLUDE_KEYWORDS = ["ジャクーバード", "ドリップ", "セット", "ギフト", "詰め合わせ", "生豆", "定期"]


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def list_product_urls():
    urls = []
    page = 1
    while True:
        soup = fetch(LIST_URL if page == 1 else LIST_URL + "page/%d/" % page)
        if soup is None:
            break
        links = soup.select("h1.entry-title a")
        if not links:
            break
        for a in links:
            if a["href"] not in urls:
                urls.append(a["href"])
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return urls


def parse_detail(url):
    soup = fetch(url)
    title = soup.select_one("h1.entry-title").get_text(strip=True)
    item = soup.select_one("#itempage")
    price_el = item.select_one(".field_price")
    m = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
    price = int(m.group(1).replace(",", "")) if m else None
    stock_text = None
    for f in item.select("div.field"):
        t = f.get_text(strip=True)
        if t.startswith("在庫状態"):
            stock_text = t.split(":", 1)[-1].strip()
    # 100gの選択肢の価格(最小重量)
    weight_g = None
    for o in item.select("select.iopt_select option"):
        mm = re.match(r"(\d+)g（([\d,]+)円）", o.get("value", ""))
        if mm:
            weight_g = int(mm.group(1))
            price = int(mm.group(2).replace(",", ""))
            break
    text = item.select_one(".exp").get_text("\n", strip=True) if item.select_one(".exp") else ""
    roast = None
    mr = re.search(r"焙煎度合\s*([^\n]+)", text)
    if mr:
        roast = mr.group(1).strip()
    proc = None
    mp = re.search(r"精製：([^\n]+)", text) or re.search(r"製法\s*([^\n]+)", text)
    if mp:
        proc = mp.group(1).strip()
    block = []
    for key in ("地域", "標高", "品種"):
        mk = re.search(key + r"：([^\n]*)", text)
        if mk and mk.group(1).strip():
            block.append("%s：%s" % (key, mk.group(1).strip()))
    bq = item.select_one(".exp blockquote")
    flavor = None
    if bq:
        lines = [l.strip() for l in bq.get_text("\n").split("\n") if l.strip()]
        lines = [l for l in lines if not l.startswith(("製法", "焙煎度合")) and "値上げ" not in l]
        flavor = " ".join(lines[:3]) or None
    parsed = parse_product(re.sub(r"\s+", " ", title))
    parsed = apply_category_hint_fallback(parsed, title)
    if "デカフェ" in title:
        parsed["category"] = "デカフェ"
    if not parsed["processing_method"]:
        parsed["processing_method"] = detect_processing_method(proc or "")
    out = bool(stock_text) and ("在庫有り" not in stock_text and "在庫僅少" not in stock_text)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast,
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": "、".join(block) or None,
        "flavor_notes": flavor,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if not out else "一時的に品切れ",
        "out_of_stock": out,
        "product_url": url,
        "stock_text": stock_text,
    }


if __name__ == "__main__":
    records, excluded = [], []
    for u in list_product_urls():
        d = parse_detail(u)
        time.sleep(CRAWL_DELAY_SECONDS)
        if any(k in d["raw_name"] for k in EXCLUDE_KEYWORDS):
            excluded.append(d)
            continue
        records.append(d)
    with open("data_polecafe.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records, "non_bean_products_excluded": excluded},
                  f, ensure_ascii=False, indent=2)
    print("[done] %d件 (除外%d件)" % (len(records), len(excluded)))
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_hint"], r["processing_method"], r["stock_text"])
