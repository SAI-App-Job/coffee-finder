# -*- coding: utf-8 -*-
"""
scrape_tachibanacoffee.py

橘珈琲店(https://tachicoffee.thebase.in、石川県金沢市石引4丁目5-1 Allier1階。特定商取引法表記で確認、事業者は橘 裕司)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全商品ページ(/items/<ID>)がコーヒー豆(100g)。希少ロット中心で、
SOLD OUT(item_purchasability=unpurchasable)の商品が多い。「ロー珈琲」はハゼ無し浅煎りの
超低温焙煎(ABOUTページの「独自の超低温焙煎技術」)で、商品名に「ロー珈琲」を含むものは
焙煎度を浅煎り(roast_hint=ロー珈琲(ハゼ無し浅煎り))とする。それ以外は焙煎度不明のためnull。
インフューズド(パッションフルーツ・ワイン酵母で発酵)の商品は方針により除外。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

SHOP_INFO = {
    "name": "橘珈琲店",
    "url": "https://tachicoffee.thebase.in/",
    "platform": "BASE",
    "address": "石川県金沢市石引4丁目5-1 Allier1階",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://tachicoffee.thebase.in"

import html as htmllib
import json
import re
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.I)
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


CATEGORY_OVERRIDES = {}
# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {
    "95035028": "タイ",
    "66040053": "中国",  # 雲南 天空農園
    "155856450": "フィリピン",  # カルサダコーヒー
    "46679374": "オーストラリア",  # マウンテントップ・エステート
}
EXCLUDE_WORDS = ["インフューズド", "ドリップバッグ", "セット", "定期便"]


def clean_name(item: dict):
    title = item["title"]
    if any(w in title for w in EXCLUDE_WORDS):
        return None, None
    title = re.sub(r"^(超限定入荷!|超限定)\s*", "", title)
    weight_g = None
    m = WEIGHT_PATTERN.search(title)
    if m:
        weight_g = to_grams(m.group(1), m.group(2))
        title = (title[:m.start()] + title[m.end():]).strip()
    return normalize(title), weight_g


def detect_roast(item, name, parsed):
    if "ロー珈琲" in name:
        return "浅煎り", "ロー珈琲(ハゼ無し浅煎り)"
    return parsed["roast_level"], None


def select_items(items):
    return items


def normalize(text: str) -> str:
    """全角英数・全角スペース・全角括弧を半角に揃え、空白を詰める。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def to_grams(value: str, unit: str) -> int:
    return int(float(value) * (1000 if unit.lower() == "kg" else 1))


def fetch_item_ids() -> list[str]:
    """sitemap.xmlから商品ページ(/items/<ID>)のIDを集める。"""
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>[^<]*/items/(\d+)</loc>", resp.text)


def fetch_item(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = htmllib.unescape(title_m.group(1))
    title = re.sub(r"\s*\|\s*[^|]*powered by BASE\s*$", "", title)
    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", htmllib.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    pur_m = PURCHASABILITY_PATTERN.search(html_text)
    return {
        "id": item_id,
        "title": normalize(title),
        "desc": desc,
        "price": int(price_m.group(1)) if price_m else None,
        "sold_out": bool(pur_m) and pur_m.group(1) == "unpurchasable",
    }


def build_record(item: dict) -> dict | None:
    name, weight_g = clean_name(item)
    if name is None:
        return None
    item_id = item["id"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item_id in CATEGORY_OVERRIDES:
        parsed["category"] = CATEGORY_OVERRIDES[item_id]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    roast_level, roast_hint = detect_roast(item, name, parsed)
    tags = list(parsed["post_processing_tags"])
    if any(k in name for k in ("カフェインレス", "Decafe", "Decaf", "デカフェ")) and "デカフェ" not in tags:
        tags.append("デカフェ")

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": item["desc"],
        "farm_note": None,
        "post_processing_tags": tags,
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    items = []
    for item_id in fetch_item_ids():
        try:
            item = fetch_item(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if item:
            items.append(item)
    records = []
    for item in select_items(items):
        record = build_record(item)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tachibanacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tachibanacoffee.json に出力しました")


if __name__ == "__main__":
    main()
