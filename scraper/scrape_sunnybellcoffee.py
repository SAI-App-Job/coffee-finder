# -*- coding: utf-8 -*-
"""
scrape_sunnybellcoffee.py

サニーベルコーヒー(https://sunnybell.thebase.in、石川県金沢市笠市町5-8。特定商取引法表記で確認、事業者は高松雅志)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品は7件(ルワンダ スカイヒル200g、マイルドエスプレッソ・ヘーゼルエスプレッソの
各200g/500g/1kg)。同じ銘柄が重量違いの別商品で並ぶため、最小重量(200g)の商品を代表とする。
マイルドエスプレッソ・ヘーゼルエスプレッソは商品名にブレンドの語がないがブレンド(商品説明で確認)。
焙煎度は商品説明の冒頭(「中浅煎り」「深煎り」)から取得。ヘーゼルエスプレッソは焙煎度の明記がなくnull。
200gの商品はSOLD OUTが多い(500g/1kgは販売中)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

SHOP_INFO = {
    "name": "サニーベルコーヒー",
    "url": "https://sunnybell.thebase.in/",
    "platform": "BASE",
    "address": "石川県金沢市笠市町5-8",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://sunnybell.thebase.in"

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


CATEGORY_OVERRIDES = {
    "188079": "ブレンド",   # マイルドエスプレッソ(コロンビア+ブラジルのブレンド)
    "28165297": "ブレンド",
    "28184987": "ブレンド",
    "60293451": "ブレンド",  # ヘーゼルエスプレッソ(ブレンド。ヘーゼルナッツの香り付けではない)
    "60293665": "ブレンド",
    "60293733": "ブレンド",
}
ORIGIN_OVERRIDES = {}
TITLE_WEIGHT_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*(kg|g)\b\s*(?:\([^)]*\))?\s*", re.I)


def clean_name(item: dict):
    title = item["title"]
    m = TITLE_WEIGHT_PATTERN.match(title)
    if not m:
        return None, None
    return normalize(title[m.end():]), to_grams(m.group(1), m.group(2))


def detect_roast(item, name, parsed):
    m = ROAST_PATTERN.match(item["desc"] or "")
    return (m.group(1) if m else parsed["roast_level"]), None


def select_items(items):
    """同じ銘柄が重量違いで並ぶ場合、最小重量の商品だけを代表にする。"""
    best = {}
    for item in items:
        name, weight = clean_name(item)
        if name is None or weight is None:
            continue
        if name not in best or weight < best[name][0]:
            best[name] = (weight, item)
    return [item for _, item in best.values()]


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
    with open("data_sunnybellcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sunnybellcoffee.json に出力しました")


if __name__ == "__main__":
    main()
