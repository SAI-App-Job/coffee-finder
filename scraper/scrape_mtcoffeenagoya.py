# -*- coding: utf-8 -*-
"""
scrape_mtcoffeenagoya.py

マウンテンコーヒー(愛知県名古屋市昭和区、mountaincoffee.co.jp、卸中心の炭火焙煎会社。豆の売り場は
昭和区台町2丁目27番地のビーンズショップ。直営カフェ「CAZAN珈琲店」等と合わせて11店舗未満)の
オンラインショップ(EC-FORCE系カート、/shop/products/<商品コード>)のブレンド・ストレートを取得する。

カテゴリ BLEND(/shop/product_categories/17)・STRAIGHT(/shop/product_categories/18)の商品ページを辿り、
各商品の既定バリエーション(グラム: 100g / 豆の状態: 豆のまま)の税込価格を採用する
(商品画像altと「SOLD OUT」ボタンの表示で確認)。ドリップバッグ・セット商品(set001_b)・ギフト・セミナーは除外。
"""
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "マウンテンコーヒー",
    "url": "https://mountaincoffee.co.jp/shop/",
    "platform": "EC-FORCE(独自カート)",
    "address": "愛知県名古屋市昭和区台町2丁目27番地",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10-25確認。Disallowなし)",
    "source_note": "オンラインショップ(https://mountaincoffee.co.jp/shop/)のBLEND・STRAIGHTカテゴリと各商品ページを2026-10-25に確認。"
                   "各商品の既定バリエーション(100g・豆のまま)の税込価格を採用。ドリップバッグ・セットは除外。"
                   "住所は豆の売り場「ビーンズショップ」(昭和区台町2-27)",
    "last_verified_at": "2026-10-25",
}
BASE = "https://mountaincoffee.co.jp"
CATEGORIES = [("ブレンド", f"{BASE}/shop/product_categories/17"), ("ストレート", f"{BASE}/shop/product_categories/18")]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 2
EXCLUDE_CODES = {"set001_b"}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(INTERVAL)
    return r.text


def build_record(cat, url):
    h = get(url)
    s = BeautifulSoup(h, "html.parser")
    name = re.search(r'"item_name":"([^"]+)"', h).group(1).strip()
    price = int(re.search(r'sales-price-include-tax[^>]*>&yen;([\d,]+)', h).group(1).replace(",", ""))
    alt = re.search(r'c-product_img__image"[^>]*alt="([^"]+)"', h).group(1)
    m = re.search(r"グラム: (\d+)g, 豆の状態: (\S+)", alt)
    if not m or m.group(2) != "豆のまま":
        raise ValueError(f"既定バリエーションが100g・豆のままではない: {url} {alt}")
    weight = int(m.group(1))
    sold = re.search(r'id="btn-stock-waiting-list"[^>]*style="([^"]*)"', h)
    in_stock = bool(sold and "display:none" in sold.group(1).replace(" ", ""))
    desc = (s.find("meta", attrs={"name": "description"}) or {}).get("content") or None
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip() or None
    opts = {o["id"]: o.get_text(" ", strip=True) for o in s.select('div[id^="option0"]')}
    roast_txt = next((v.split("：", 1)[1] for v in opts.values() if v.startswith("焙煎度：")), None)
    origin_txt = next((v.split("：", 1)[1] for v in opts.values() if v.startswith("生産国：")), None)
    parsed = parse_product(name)
    if cat == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        explicit = detect_country_name(name) or (detect_country_name(origin_txt) if origin_txt else None)
        if explicit:
            parsed["origin_country"] = explicit
            parsed["origin_source"] = "raw_name" if explicit in name else "description"
    if re.search(r"カフェインレス|デカフェ|ディカフェ", name):
        parsed["category"] = "デカフェ"
    roast_level = None
    if roast_txt:
        roast_level = parse_product(roast_txt)["roast_level"] or re.sub(r"[（(].*$", "", roast_txt)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": roast_txt,
        "flavor_notes": desc,
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
    for cat, curl in CATEGORIES:
        s = BeautifulSoup(get(curl), "html.parser")
        seen = []
        for a in s.select('a[href*="/shop/products/"]'):
            code = a["href"].rstrip("/").split("/")[-1]
            if code in EXCLUDE_CODES or code in seen:
                continue
            seen.append(code)
        for code in seen:
            records.append(build_record(cat, f"{BASE}/shop/products/{code}"))
    with open("data_mtcoffeenagoya.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mtcoffeenagoya.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], (r["flavor_notes"] or "")[:25])


if __name__ == "__main__":
    main()
