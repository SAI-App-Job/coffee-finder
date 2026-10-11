# -*- coding: utf-8 -*-
"""
scrape_narafujiedacoffee.py

奈良藤枝珈琲焙煎所(narafujiedacoffee.jp、フジエダ珈琲株式会社、奈良県大和郡山市大江町112-1)の
珈琲豆を取得する。Shopify の /products.json を使用。

【対象】タグ「珈琲豆」かつタイトル末尾が「(豆)」のブレンド4種(各200g)。
粉は同一銘柄の別バリエーションのため除外。ギフト・缶セット、ドリップバッグ、
カフェオレベース、水出し珈琲、器具は除外。内容量は商品ページの「内容量:200g」表記。
"""
import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

SHOP_INFO = {
    "name": "奈良藤枝珈琲焙煎所",
    "url": "https://narafujiedacoffee.jp/",
    "platform": "Shopify",
    "address": "奈良県大和郡山市大江町112-1",
    "prefecture": "奈良県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}
BASE_URL = "https://narafujiedacoffee.jp"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}


def get_weight(handle):
    r = requests.get(f"{BASE_URL}/products/{urllib.parse.quote(handle)}", headers=HEADERS, timeout=30)
    t = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    m = re.search(r"内容量[:：]\s*(\d+)\s*[gｇ]", t)
    return int(m.group(1)) if m else None


def scrape_all_products():
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    records = []
    for p in resp.json()["products"]:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "珈琲豆" not in (p.get("tags") or []) or "ギフトセット" in (p.get("tags") or []):
            continue
        if not title.endswith("(豆)"):
            continue
        name = title[: -len("(豆)")].strip()
        v = p["variants"][0]
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None
        roast = "中煎り" if "中煎り" in body else None
        category = "デカフェ" if "カフェインレス" in name else "ブレンド"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": category,
            "origin_country": None,
            "origin_source": None,
            "designated_brand": None,
            "processing_method": None,
            "grade": None,
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": [],
            "blend_components": [],
            "price": int(float(v["price"])),
            "weight_g": get_weight(p["handle"]),
            "stock_status": "販売中" if v.get("available") else "完売",
            "out_of_stock": not v.get("available"),
            "product_url": f"{BASE_URL}/products/{urllib.parse.quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_narafujiedacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_narafujiedacoffee.json に出力しました")


if __name__ == "__main__":
    main()
