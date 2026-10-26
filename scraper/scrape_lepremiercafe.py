# -*- coding: utf-8 -*-
"""
scrape_lepremiercafe.py

Le Premier Cafe(ル プルミエ カフェ、le-premier-cafe.com。心斎橋本店 大阪府大阪市中央区心斎橋筋1-3-28
ビギ1stビル3F、なんばロースタリー、淡路島の3店舗、運営は株式会社Keep running)のオンラインショップから
珈琲豆の商品情報を取得する。WordPress + WooCommerce。

【取得方法】robots.txt は /wp-json/ を Disallow しているため WooCommerce Store API は使わない
(許可された /product-cat/item-category/coffee-bean/ のHTMLと各商品ページのみ取得)。
カテゴリ「珈琲豆」の一覧から商品を集め、各商品ページの data-product_variations(JSON)の
Size × 豆の種類(豆のまま/粉にする)から、最小サイズ(100g)・豆のままの価格と在庫を採用する。
コーヒーバッグ・ドリップバッグ・リキッド・アパレル・ギフトは対象外。間隔は2秒。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "Le Premier Cafe",
    "url": "https://le-premier-cafe.com/",
    "platform": "WordPress + WooCommerce",
    "address": "大阪府大阪市中央区心斎橋筋1-3-28 ビギ1stビル3F",
    "prefecture": "大阪府",
    "robots_txt_status": "取得可(/wp-json/・/?s=・add-to-cart 等はDisallow。API不使用でHTMLのみ取得)",
    "source_note": "公式 https://le-premier-cafe.com/product-cat/item-category/coffee-bean/ と各商品ページを2026-10-26に確認。店舗は心斎橋本店・なんばロースタリー・淡路島の3店。2026年秋の新商品(ブラジル フクダ農園)掲載あり。",
    "last_verified_at": "2026-10-26",
}

CATEGORY_URL = "https://le-premier-cafe.com/product-cat/item-category/coffee-bean/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_WORDS = ("極深煎り", "中深煎り", "中浅煎り", "浅煎り", "中煎り", "深煎り")
INTERVAL = 2.0


def get(url: str) -> str:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_products() -> list[tuple[str, str]]:
    text = get(CATEGORY_URL)
    out = []
    for m in re.finditer(r'data-product-id="(\d+)" data-product-name="([^"]*)">\s*<div class="box__thumb">\s*<a href="([^"]+)"', text):
        name, url = m.group(2), m.group(3)
        if "【珈琲豆】" in name and all(url != u for _, u in out):
            out.append((name, url))
    return out


def clean_name(raw: str) -> str:
    import html
    name = html.unescape(raw).replace("【珈琲豆】", "")
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" - ", " ").replace("–", " ")
    return re.sub(r"\s+", " ", name).strip()


def build_record(raw_name: str, url: str) -> dict | None:
    soup = BeautifulSoup(get(url), "html.parser")
    form = soup.find("form", class_="variations_form")
    if not form or not form.get("data-product_variations"):
        return None
    cands = []
    for v in json.loads(form["data-product_variations"]):
        attrs = v["attributes"]
        size = attrs.get("attribute_size")
        kind = next((val for k, val in attrs.items() if k != "attribute_size"), "")
        m = re.match(r"^(\d+)\s*g", size or "")
        if not m or kind not in ("豆のまま", ""):
            continue
        cands.append((int(m.group(1)), v))
    if not cands:
        return None
    w, v = min(cands, key=lambda x: x[0])
    body = soup.find("body")
    lines = body.get_text("\n", strip=True).split("\n") if body else []
    # 商品ページ冒頭のパンくず状の行(珈琲豆 / ブレンド / 中煎り / 商品名)から焙煎度とブレンドを判定する
    ti = next((i for i, ln in enumerate(lines) if ln.startswith("【珈琲豆】")), None)
    crumbs = lines[max(0, ti - 4):ti] if ti is not None else []
    roast = next((ln for ln in crumbs if ln in ROAST_WORDS), None)
    is_blend = "ブレンド" in crumbs
    flavor = None
    for i, ln in enumerate(lines):
        if ln == "FLAVOR" and i + 1 < len(lines):
            flavor = lines[i + 1]
            break
    name = clean_name(raw_name)
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
    in_stock = bool(v.get("is_in_stock"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": (flavor or "")[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(v["display_price"]) if v.get("display_price") is not None else None,
        "weight_g": w,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for raw, url in collect_products():
        rec = build_record(raw, url)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_lepremiercafe.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lepremiercafe.json に出力しました")


if __name__ == "__main__":
    main()
