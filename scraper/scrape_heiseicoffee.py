# -*- coding: utf-8 -*-
"""
scrape_heiseicoffee.py

平成珈琲(heisei-coffee.co.jp、兵庫県神戸市中央区中町通2-2-18 平戸ビル(本社・本店)、
焙煎工房は神戸市兵庫区)の商品情報を取得する。WordPress + WooCommerce
(Store API /wp-json/wc/store/v1/products?per_page=100)。

【商品構造について】
実データ確認済み(2026-10時点、全62件): 重量・挽き方ごとに別々のWooCommerce単純商品
(例: 「Brazil 【豆】100g」「Brazil 【豆】200g」「Brazil 【粉】100g」)として登録されており、
バリエーションは使われていない。このため、名称から重量(100g/200g/50g)と形態(豆/粉)を
読み取り、豆の商品を基本名でグルーピングして最小重量の商品(通常100g。ブレンド等は
200gのみ)の価格・在庫・URLを代表とする。

【除外対象】
粉の商品、ドリップバッグ、リキッドアイスコーヒー、ギフト・詰め合わせ・セット
(「【平成珈琲の週替わりコーヒー】各一種【豆】200g入り」はブレンドとスペシャリティの
2種セットのため除外)、粉のみの商品。
ゲイシャ(パナマ ラ エスメラルダ農園)とコピルアクは50g・100gの2商品があるため、
基本名を統一して最小重量(50g)を代表とする。

【価格】商品ページに「(税込)」表記あり(`price_html`にも税込サフィックス)。
【産地・焙煎度】short_description内の「生産国/原産国」「焙煎度」「精製方法」の
構造化表記から取得する。
"""

import html
import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "平成珈琲",
    "url": "https://www.heisei-coffee.co.jp/",
    "platform": "WordPress + WooCommerce",
    "address": "兵庫県神戸市中央区中町通2-2-18 平戸ビル",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

API_URL = "https://www.heisei-coffee.co.jp/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["ドリップバッグ", "リキッド", "ギフト", "セット", "詰め合わせ", "各一種", "週替わり", "粉"]
BEAN_MARK = re.compile(r"[【\[（(]\s*豆\s*[】\]）)]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gG]")
# 同一商品の50g/100g等の表記ゆれ(接頭辞・農園名の差)を統一するための名称マップ
NAME_OVERRIDES = {
    "エスメラルダ": "パナマ ラ エスメラルダ農園 ゲイシャ2025 Private Collection",
    "コピルアク": "コピルアク(幻の珈琲)",
}


def fetch_products() -> list[dict]:
    products, page = [], 1
    while True:
        resp = requests.get(API_URL, params={"per_page": 100, "page": page}, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def base_name(raw: str) -> str:
    """商品名から【豆】・重量・宣伝文の接頭辞を取り除いた基本名を返す。"""
    name = unicodedata.normalize("NFKC", html.unescape(raw))
    for kw, fixed in NAME_OVERRIDES.items():
        if kw in name:
            return fixed
    name = BEAN_MARK.sub(" ", name)
    name = re.sub(r"\d+\s*[gG](入り)?", " ", name)
    # 「完売!」「6月焙煎後発送!」等の宣伝接頭辞(!で終わる句)を除去
    name = re.sub(r"^(?:[^!]*!)+", "", name)
    name = re.sub(r"\s+", " ", name).strip(" 　")
    return name


def build_record(name: str, group: list[dict]) -> dict:
    # 最小重量(同重量なら在庫あり優先)
    rep = min(group, key=lambda x: (x["weight"], not x["p"]["is_in_stock"]))
    p, weight = rep["p"], rep["weight"]
    short = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
    short = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", short))
    long_ = BeautifulSoup(p.get("description") or "", "html.parser").get_text(" ", strip=True)
    long_ = re.sub(r"\s+", " ", long_)
    desc_long = re.split(r"味覚チャート", long_)[0].strip()
    flavor_notes = (desc_long or None)
    if flavor_notes:
        flavor_notes = flavor_notes[:400]

    is_blend = ("ブレンド" in name) or ("blend" in name.lower()) or ("ブレンドコーヒー" in [c["name"] for c in p["categories"]])
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        m = re.search(r"(?:生産国|原産国)[：:]\s*(\S+)", short)
        if not parsed["origin_country"] and m:
            c = detect_country_name(m.group(1))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    extra = extract_from_description(re.sub(r"(精製方法)", r"\n\1", short))
    processing = parsed["processing_method"] or extra["processing_method"]

    roast_hint = None
    m = re.search(r"焙煎度?[：:]\s*([^\s(]+(?:\s*\([^)]*\))?)", short, re.I)
    if m:
        roast_hint = m.group(1)
    roast_level = parsed["roast_level"]
    if not roast_level and roast_hint:
        roast_level = parse_product(roast_hint)["roast_level"]

    in_stock = bool(p["is_in_stock"])
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(p["prices"]["price"]) if p["prices"].get("price") else None,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def scrape_all_products() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for p in fetch_products():
        raw = html.unescape(p["name"])
        norm = unicodedata.normalize("NFKC", raw)
        if any(kw in norm for kw in EXCLUDE_KEYWORDS):
            continue
        if not BEAN_MARK.search(norm):
            continue
        m = WEIGHT_PATTERN.search(norm)
        if not m:
            continue
        key = base_name(raw)
        groups.setdefault(key, []).append({"p": p, "weight": int(m.group(1))})
    return [build_record(name, g) for name, g in groups.items()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_heiseicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_heiseicoffee.json に出力しました")


if __name__ == "__main__":
    main()
