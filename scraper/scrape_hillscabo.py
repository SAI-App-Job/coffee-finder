# -*- coding: utf-8 -*-
"""
scrape_hillscabo.py

ヒルズ珈房(Coffee Factory Hill's Cabo、運営:町田焙煎珈琲株式会社、shop.hillscabo.com、東京都
町田市本町田3450-12・鶴川街道沿い、市内カフェ・レストラン向けに業務用コーヒーを提供する
焙煎会社の小売店)の商品情報を取得する。カラーミーショップ(charset=euc-jp、
`resp.encoding = "euc-jp"`を明示)。店舗は1店舗。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ブレンドコーヒー」(cbid=1077157)・「シングルコーヒー」
(cbid=1077158)の豆商品のみ(商品画像の最終更新は2026-06)。マイドリップバッグ・ドリップバッグ・
アイスコーヒー(水出し)・紅茶・スイーツ・ギフトは対象外。
同一銘柄が「(250g)」「(500g)」「(1kg)」の別商品として並ぶ(銘柄+焙煎度が同じもの)ため、
最小サイズの商品だけを代表として採用する(マンデリンTABOO・キリマンジャロの雪は100gあり)。
「コロンビアスタイル」は[中煎り]250gと[浅煎り＋極深煎り]100g(同じコロンビアを異なる焙煎度で
焙煎してブレンド)が別銘柄として並ぶので別商品として扱う。

【価格・在庫】
一覧の税込価格(例:「1,875円(本体1,736円、税139円)」の1,875円)。在庫は「SOLD OUT」表示で判定。
焙煎度は商品名の[中浅煎り]等から取りroast_hintに保持する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ヒルズ珈房",
    "url": "https://shop.hillscabo.com/",
    "platform": "カラーミーショップ",
    "address": "東京都町田市本町田3450-12",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://shop.hillscabo.com"
CATEGORIES = [("ブレンドコーヒー", "1077157"), ("シングルコーヒー", "1077158")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップバッグ", "ドリップバック", "水出し", "ギフト", "セット", "かりんとう")
MAX_PAGES = 5
NAME_PATTERN = re.compile(r"^(?P<base>.+?)(?P<roast>\[[^\]]+\])?\s*[（(](?P<size>\d+(?:\.\d+)?)\s*(?P<unit>kg|g)[）)]\s*(?P<tail>.*)$", re.I)
ORIGIN_OVERRIDES = {"ミネラル栽培": "ブラジル", "TABOO": "インドネシア", "レッドマウンテン": "ケニア", "グァテアマラ": "グアテマラ"}


def fetch(url: str) -> str | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for label, cbid in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0" + ("" if page == 1 else f"&page={page}")
            html_text = fetch(url)
            if html_text is None:
                break
            soup = BeautifulSoup(html_text, "html.parser")
            new = 0
            for box in soup.select("div.products-list div.box"):
                a = box.select_one("a[href*='pid=']")
                name_el = box.select_one("p.name")
                if not (a and name_el):
                    continue
                m = re.search(r"pid=(\d+)", a["href"])
                if not m or m.group(1) in items:
                    continue
                new += 1
                price_el = box.select_one("p.price")
                pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
                desc = box.select_one("p.description")
                items[m.group(1)] = {
                    "pid": m.group(1),
                    "name": re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "desc": desc.get_text(strip=True) if desc else None,
                    "sold_out": "SOLD OUT" in box.get_text(),
                    "group": label,
                }
            if new == 0:
                break
    return list(items.values())


def split_name(name: str) -> dict | None:
    norm = unicodedata.normalize("NFKC", name)
    m = NAME_PATTERN.match(norm)
    if not m:
        return None
    size = float(m.group("size")) * (1000 if m.group("unit").lower() == "kg" else 1)
    base = m.group("base").strip()
    roast = (m.group("roast") or "").strip("[]") or None
    # 銘柄キー=名前+焙煎度(サイズ違いを同一視)。ブレンドは「・まちだ名産品」付きの名前のまま
    return {"base": base, "roast": roast, "size": int(size), "key": f"{base}|{roast or ''}"}


def build_record(item: dict, parts: dict) -> dict | None:
    base = parts["base"]
    parsed = parse_product(base)
    if item["group"] == "ブレンドコーヒー" or "ブレンド" in base:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, base)
        if not parsed["origin_country"]:
            c = detect_country_name(base) or next((v for k, v in ORIGIN_OVERRIDES.items() if k in base), None)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
    display = base + (f"[{parts['roast']}]" if parts["roast"] else "")
    out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": parts["roast"],
        "flavor_notes": item["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": parts["size"],
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[dict, dict]] = {}
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        parts = split_name(item["name"])
        if parts is None:
            print(f"[skip] 名前解析不可: {item['name']}")
            continue
        cur = best.get(parts["key"])
        if cur is None or parts["size"] < cur[1]["size"]:
            best[parts["key"]] = (item, parts)
    return [build_record(item, parts) for item, parts in best.values()]


def main():
    records = [r for r in scrape_all_products() if r]
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hillscabo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hillscabo.json に出力しました")


if __name__ == "__main__":
    main()
