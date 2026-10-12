# -*- coding: utf-8 -*-
"""
scrape_umibouzu.py

Sea Side Cafe うみぼうず(umibouzu-cafe.com、石川県加賀市片野町3-6、自家焙煎珈琲専門カフェ)の
通販コーヒー豆を取得する。WordPress + Welcart(クラス名 usces / skuform / zaikostatus)。

【構成】商品は6銘柄(ブラジル/タンザニア/ガテマラ/コロンビア/深海ブレンド/ブレンド珈琲)。
商品ページ /item/<slug> は 2021/01/<slug>/ へ301リダイレクトされる。
各商品に 200g(¥1,728)と 500g(¥4,320)の2 SKU(form.skuform)があり、ここでは最小重量の
200gを代表として採用する(100g設定は無い)。
在庫は各SKUの div.zaikostatus「在庫状態 : 在庫有り」から判定する。
焙煎度は商品ページに記載が無く null(「その豆の持つ美味しさが一番美味しい焙煎度合い」との記述のみ)。

robots.txt は 403 Forbidden を返す(2026-10-12確認)ため規定なしとして扱い、商品6ページのみを低頻度で取得する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, apply_category_hint_fallback

SHOP_INFO = {
    "name": "Sea Side Cafe うみぼうず",
    "url": "https://umibouzu-cafe.com/",
    "platform": "WordPress + Welcart",
    "address": "石川県加賀市片野町3-6",
    "prefecture": "石川県",
    "robots_txt_status": "不明(2026-10-12確認。robots.txt自体が403 Forbidden)",
}

BASE = "https://umibouzu-cafe.com/item/"
SLUGS = ["brasil01", "tanzania01", "guatemala01", "colpmbia0", "hukaumi01", "blend-2"]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[）)]")
PRICE_PATTERN = re.compile(r"[¥￥]\s*([\d,]+)")
# 商品名は「ガテマラ」表記だが、本アプリの標準は「グアテマラ」(coffee_parser側で正規化される)
FIRST_LINE_SPLIT = re.compile(r"\s")


def fetch_product(slug):
    resp = requests.get(BASE + slug, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    skus = []
    for form in soup.select("div.skuform"):
        title = form.get_text(" ", strip=True)
        m_w = WEIGHT_PATTERN.search(title)
        m_p = PRICE_PATTERN.search(form.get_text(" ", strip=True))
        stock_el = form.select_one("div.zaikostatus")
        name = WEIGHT_PATTERN.sub("", title.split("豆の状態")[0]).strip()
        skus.append({
            "name": name,
            "weight": int(m_w.group(1)) if m_w else None,
            "price": int(m_p.group(1).replace(",", "")) if m_p else None,
            "stock_text": stock_el.get_text(strip=True) if stock_el else "",
        })
    desc_el = soup.select_one("div.item-description")
    desc = " ".join(desc_el.get_text(" ", strip=True).split()) if desc_el else ""
    return resp.url, skus, desc


def build_record(url, skus, desc):
    skus = [s for s in skus if s["weight"]]
    s = min(skus, key=lambda x: x["weight"])
    name = s["name"]
    # 説明冒頭の「ブラジル　トミオフクダ　ブルボン」等の見出し行を産地判定の補助に使う
    head = desc[:60]
    parsed = parse_product(name)
    if not parsed["origin_country"] and parsed["category"] != "ブレンド":
        parsed = apply_category_hint_fallback(parsed, head)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    structural_out = "有り" not in s["stock_text"] and "あり" not in s["stock_text"]
    stock_status = detect_stock_status(name, structural_out)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": None,
        "flavor_notes": desc[:400] or None,
        "blend_components": [],
        "price": s["price"],
        "weight_g": s["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products():
    records = []
    for slug in SLUGS:
        url, skus, desc = fetch_product(slug)
        records.append(build_record(url, skus, desc))
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_umibouzu.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_umibouzu.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["stock_status"], r["product_url"])
