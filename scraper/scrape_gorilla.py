# -*- coding: utf-8 -*-
"""
scrape_gorilla.py

自家焙煎珈琲 ごりら(愛知県東海市、gorillacoffee-1101.com)の珈琲豆カテゴリを取得する。
WordPress + WooCommerce だが Store API(/wp-json/wc/store/v1/products)は404のため、
カテゴリ一覧(/products/beans/)から商品ページ(/product/<id>/)を辿り、各ページの
data-product_variations(容量: 100〜500g)から最小容量(通常100g)の価格・在庫を採用する。
「お試しセット」は除外。ドリップバッグは別カテゴリ(/products/drip/)なので対象外。
"""
import html
import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲 ごりら",
    "url": "https://gorillacoffee-1101.com/",
    "platform": "WordPress + WooCommerce",
    "address": "愛知県東海市大田町寺下93-1 ニッチェル大橋",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10-21確認。/wp-admin/ のみ禁止)",
    "source_note": "公式サイトの珈琲豆カテゴリ(https://gorillacoffee-1101.com/products/beans/)と各商品ページを2026-10-21に確認。"
                   "公式ブログの最新記事は2026-06-18。各銘柄の100g(最小容量)・豆のままの価格を採用。お試しセット・ドリップバッグは除外",
    "last_verified_at": "2026-10-21",
}
LIST_URL = "https://gorillacoffee-1101.com/products/beans/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 2


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(INTERVAL)
    return r.text


def list_product_urls():
    urls = []
    page = 1
    while True:
        u = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
        try:
            s = BeautifulSoup(get(u), "html.parser")
        except requests.HTTPError:
            break
        found = []
        for a in s.select('a[href*="/product/"]'):
            href = urljoin(u, a["href"])
            if re.search(r"/product/\d+/?$", href) and href not in urls and href not in found:
                found.append(href)
        if not found:
            break
        urls.extend(found)
        page += 1
    return urls


def build_record(url):
    s = BeautifulSoup(get(url), "html.parser")
    name = re.sub(r"\s+", " ", s.select_one("h1.product_title").get_text(" ", strip=True).replace("　", " ")).strip()
    if "セット" in name:
        return None
    form = s.select_one("form.variations_form")
    variations = json.loads(html.unescape(form["data-product_variations"]))
    cands = []
    for v in variations:
        w = v["attributes"].get("attribute_pa_youryou")
        if w and w.isdigit():
            cands.append((int(w), v))
    if not cands:
        return None
    weight, v = min(cands, key=lambda t: t[0])
    price = int(v["display_price"])
    in_stock = bool(v.get("is_in_stock"))
    desc_el = s.select_one(".c-detail-data__desc")
    desc = desc_el.get_text("\n", strip=True) if desc_el else ""
    m = re.search(r"焙煎度[:：]\s*(\S+)", desc)
    roast = m.group(1) if m else None
    proc = re.search(r"精製方法[:：]\s*(\S+)", desc)
    parsed = parse_product(name)
    parsed["category"] = "ストレート"
    parsed = apply_category_hint_fallback(parsed, name)
    explicit = detect_country_name(name)
    if explicit:
        parsed["origin_country"] = explicit
        parsed["origin_source"] = "country_name"
    if not parsed["origin_country"] and name.startswith("中国"):
        parsed["origin_country"] = "中国"
        parsed["origin_source"] = "raw_name"
    # 風味説明(「焙煎度」以降の最初の説明段落)
    lines = [l for l in desc.split("\n") if l and not re.match(r"^(商品説明|苦味|酸味|濃度|焙煎度|精製方法|品種)[:：]", l)]
    lines = [l for l in lines if "★" not in l and re.search(r"甘|酸|香|風味|フレーバー|味わい", l)]
    flavor = lines[0][:300] if lines else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or (proc.group(1) if proc else None),
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": roast,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def main():
    records = []
    for u in list_product_urls():
        rec = build_record(u)
        if rec:
            records.append(rec)
    with open("data_gorilla.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gorilla.json に出力しました")
    for r in records:
        print(r["raw_name"], r["origin_country"], r["roast_level"], r["processing_method"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
