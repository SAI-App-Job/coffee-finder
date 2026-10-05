# -*- coding: utf-8 -*-
"""
scrape_ikiteirucoffee.py

生きている珈琲(ikiteiru.com、京都府京都市下京区立売東町24 みのや四条ビルB1F、
株式会社 生きている珈琲)の商品情報を取得する。ショップサーブ(ShopServe、UTF-8)。

【対象商品について】
実データ確認済み(2026-10時点): 「全ての焙煎度」(/SHOP/33556/list.html、list2/list3.html)の
全22件はすべて100gの焙煎豆(ブレンド・シングルオリジン)で、全件を対象とする。
ドリップバッグ(カテゴリ34770)・器具(カテゴリ50435)は別カテゴリのため最初から対象外。
価格は税込。同一銘柄の複数サイズ展開は無い(「深煎りモカ」と「モカ」等は焙煎度違いの
別商品)。

【商品詳細ページについて】
各商品ページに「原産国/銘柄/グレード/精製方法/品種/焙煎度」の構造化表記があるため、
産地・精製方法・グレード・焙煎度・品種(farm_note)をそこから取得する。在庫は
「在庫:」セルの記号(○など)で判定し、×・売り切れ・在庫切れ表記なら完売とする。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "生きている珈琲",
    "url": "https://ikiteiru.com/",
    "platform": "ショップサーブ",
    "address": "京都府京都市下京区立売東町24 みのや四条ビルB1F",
    "prefecture": "京都府",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://ikiteiru.com"
LIST_URL = f"{BASE_URL}/SHOP/33556/list.html"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップバッグ", "ドリップバック", "セット", "ギフト", "ドリッパー")
MAX_PAGES = 10
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
FIELD_PATTERN = re.compile(r"^(原産国|銘柄|生産地区|グレード|精製方法|品種|焙煎度)\s*『([^』]*)』")
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else LIST_URL.replace("list.html", f"list{page}.html")
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for card in soup.select("section.column4"):
            a = card.select_one("h2 a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            price_el = card.select_one("span.selling_price")
            price_m = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
            items.append({
                "title": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "path": href,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "list_desc": re.sub(r"\s+", " ", card.select_one("p.inner-catch").get_text(" ", strip=True))
                if card.select_one("p.inner-catch") else None,
            })
        if new == 0:
            break
    return items


def fetch_detail(path: str) -> dict:
    soup = BeautifulSoup(fetch(BASE_URL + path), "html.parser")
    for e in soup(["script", "style"]):
        e.decompose()
    stock_text = None
    for th in soup.find_all("th"):
        if th.get_text(strip=True).startswith("在庫"):
            td = th.find_next_sibling("td")
            stock_text = td.get_text(strip=True) if td else None
            break
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    fields = {}
    notes = []
    for l in lines:
        l = unicodedata.normalize("NFKC", l) if FIELD_PATTERN.match(unicodedata.normalize("NFKC", l)) else l
        m = FIELD_PATTERN.match(l)
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2).strip()
    return {"fields": fields, "stock_text": stock_text, "lines": lines}


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label
    return None


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", title)
    wm = WEIGHT_PATTERN.search(norm)
    weight_g = int(wm.group(1)) if wm else None
    name = re.sub(r"\s*《[^》]*》\s*", "", norm)
    name = re.sub(r"^【オンライン限定】\s*", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    detail = fetch_detail(item["path"])
    fields = detail["fields"]
    stock_text = detail["stock_text"] or ""
    sold_out = any(k in stock_text for k in ("×", "✕", "切れ", "なし", "完売", "売り切れ"))

    country_field = unicodedata.normalize("NFKC", fields.get("原産国", ""))
    is_blend = "ブレンド" in name or "+" in country_field
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(country_field) if country_field else None
        if c:
            parsed["origin_country"], parsed["origin_source"] = c, "description"
        elif not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_raw = fields.get("焙煎度")
    roast_level = coarse_roast(roast_raw) or coarse_roast(name)
    # 「浅煎り(ミディアムロースト)」等の括弧内は原文のままroast_hintに残す
    roast_hint = unicodedata.normalize("NFKC", roast_raw) if roast_raw else None

    processing = None
    if fields.get("精製方法") and not is_blend:
        raw = unicodedata.normalize("NFKC", fields["精製方法"])
        processing = detect_processing_method(raw) or raw
    elif not is_blend:
        processing = parsed["processing_method"]

    grade = parsed["grade"]
    if fields.get("グレード") and not grade:
        g = unicodedata.normalize("NFKC", fields["グレード"]).strip()
        grade = g if g not in ("ー", "-", "―", "") else None
    elif grade in ("ー", "-", "―"):
        grade = None

    farm_parts = []
    for key, label in (("銘柄", "銘柄"), ("生産地区", "生産地区"), ("品種", "品種")):
        if fields.get(key):
            farm_parts.append(f"{label}: {unicodedata.normalize('NFKC', fields[key])}")
    if is_blend and country_field:
        farm_parts.append(f"原産国: {country_field}")

    blend_components = []
    if is_blend and country_field:
        for part in country_field.split("+"):
            c = detect_country_name(part)
            if c:
                blend_components.append({"origin_country": c})

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": grade,
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": item["list_desc"],
        "farm_note": " / ".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['path']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ikiteirucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ikiteirucoffee.json に出力しました")


if __name__ == "__main__":
    main()
