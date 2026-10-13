# -*- coding: utf-8 -*-
"""
scrape_potohoto.py

COFFEE potohoto(www.potohoto.jp、沖縄県那覇市安里388-1 栄町市場内。ネット店の焙煎・発送は
同店。住所は特商法表記)の商品情報を取得する。MakeShop(EUC-JP、旧形式 /shopdetail/)。

【対象商品について】
実データ確認済み(2026-10時点): 商品カテゴリのうち「シングル＊まろやか」(007)・
「シングル＊コク・深み」(006)・「オリジナルブレンド」(008)の一覧ページ(いずれも1ページ完結)
を対象とする。同一銘柄が重量違い(50g/100g/240g/250g/500g)の別商品として並ぶため、
商品名末尾の重量を除いた基準名でグルーピングし、最小重量の商品を代表とする。
- 除外: 水出しアイスパック(COLD BREW MINI)、珈琲器具＆雑貨(009)、珈琲豆ギフト(ct55)、
  ドリップパック(ct76)、包装・袋追加、コラボスペシャル(ct75、商品なし)。
- 価格は一覧の「価格(税込)」、説明は詳細ページの og:description、在庫は商品名の
  「(品切れ)」表示で判定する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "COFFEE potohoto",
    "url": "https://www.potohoto.jp/",
    "platform": "MakeShop",
    "address": "沖縄県那覇市安里388-1(栄町市場内)",
    "prefecture": "沖縄県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.potohoto.jp"
LIST_PAGES = [
    ("/shopbrand/007/X/", "ストレート"),
    ("/shopbrand/006/X/", "ストレート"),
    ("/shopbrand/008/X/", "ブレンド"),
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ("COLD BREW", "水出し", "ギフト", "ドリップ", "セット", "フレンチプレス")
WEIGHT_TAIL = re.compile(r"\s*(\d+)\s*g\s*$", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
PROCESS_LINE = re.compile(r"精製\s*[:：]\s*([^/\]］\s]+)")
ITEM_ID = re.compile(r"/shopdetail/([0-9]+)/")
PRICE = re.compile(r"([\d,]+)\s*円")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def parse_list(path: str, default_category: str) -> list[dict]:
    soup = fetch(BASE_URL + path)
    items, seen = [], set()
    for a in soup.find_all("a", href=ITEM_ID):
        name_raw = a.get_text(strip=True)
        if not name_raw:
            continue
        item_id = ITEM_ID.search(a["href"]).group(1)
        if item_id in seen:
            continue
        seen.add(item_id)
        table = a.find_parent("table")
        text = re.sub(r"\s+", " ", table.get_text(" ", strip=True)) if table else ""
        name = unicodedata.normalize("NFKC", name_raw)
        sold_out = "品切れ" in name or "品切れ" in text.split("価格")[0]
        name = re.sub(r"\(品切れ\)", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        m = re.search(r"価格\s*:\s*([\d,]+)\s*円", text)
        wm = WEIGHT_TAIL.search(name)
        if not (m and wm):
            continue
        items.append({
            "id": item_id,
            "name": name,
            "base_name": WEIGHT_TAIL.sub("", name).strip(),
            "key": re.sub(r"\s+", "", WEIGHT_TAIL.sub("", name)).lower(),
            "weight_g": int(wm.group(1)),
            "price": int(m.group(1).replace(",", "")),
            "out_of_stock": sold_out,
            "category": default_category,
        })
    return items


def fetch_detail(item_id: str) -> dict:
    soup = fetch(f"{BASE_URL}/shopdetail/{item_id}/")
    og = soup.find("meta", property="og:description")
    desc = re.sub(r"\s+", " ", og["content"]).strip() if og and og.get("content") else None
    pm = soup.find("meta", property="product:price:amount")
    price = int(pm["content"]) if pm and pm.get("content", "").isdigit() else None
    return {"desc": desc, "price": price}


def build_record(item: dict, detail: dict) -> dict:
    display = item["base_name"]
    display = re.sub(r"^potohoto", "potohoto ", display)
    parsed = parse_product(display)
    if item["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(display)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, display)
    desc = detail["desc"]
    roast_level = parsed["roast_level"]
    rm = ROAST_PATTERN.search(display)
    if rm:
        roast_level = rm.group(1)
    processing = parsed["processing_method"]
    if not processing and desc:
        pm = PROCESS_LINE.search(desc)
        if pm:
            processing = detect_processing_method(pm.group(1))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc[:400] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"] or item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if item["out_of_stock"] else "販売中",
        "out_of_stock": item["out_of_stock"],
        "product_url": f"{BASE_URL}/shopdetail/{item['id']}/",
    }


def scrape_all_products() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for path, cat in LIST_PAGES:
        for item in parse_list(path, cat):
            if any(k.lower() in item["name"].lower() for k in NON_BEAN_KEYWORDS):
                continue
            groups.setdefault(item["key"], []).append(item)
    records = []
    for base_name, items in groups.items():
        rep = min(items, key=lambda x: x["weight_g"])
        try:
            detail = fetch_detail(rep["id"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {rep['id']} ({e})")
            detail = {"desc": None, "price": None}
        records.append(build_record(rep, detail))
        time.sleep(1)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_potohoto.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_potohoto.json に出力しました")


if __name__ == "__main__":
    main()
