# -*- coding: utf-8 -*-
"""
scrape_windfarm.py

ウインドファーム(株式会社ウインドファーム、福岡県遠賀郡水巻町下二西3-7-16、フェアトレード・有機栽培
コーヒーの自社焙煎。ご注文を受けてから焙煎。直営店「珈琲工房ウインドファーム+」が水巻町)の
直営通販(www.organic-coffee.jp、MakeShop)の商品情報を取得する。

【対象商品について】
カテゴリ「レギュラーコーヒー豆」(/view/category/ct1、2026-10-20時点16件)の豆の単品を収録する。
除外: 「100g飲みきりバラエティコーヒーセット」(セット)、タンナコーヒー(バヌアツの生産地で焙煎済みを輸入
しており自家焙煎ではない)。粉・生豆・ドリップバッグ・水出し・紅茶・器具・業務用は別カテゴリで対象外。
各銘柄は1サイズ販売(100g/170g/200g)のため表示価格(税込)をそのまま採用。在庫は一覧の「SOLD OUT」表示
(3件: トセパン[4月末販売終了]・レイジーマン・スペシャルカルロスさん)。
複数産地表記(原産地:A、B、…)はブレンドとして扱う。
焙煎度は、商品ページに「深煎り焙煎になっています」「焙煎度合いは深煎りです」とある銘柄のみ深煎りとし、
中煎/深煎/極深煎を選べる銘柄は None(注文時に選択)。
サイトの文字コードは実際には UTF-8(2026-10-20確認)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ウインドファーム",
    "url": "https://www.organic-coffee.jp/",
    "platform": "MakeShop",
    "address": "福岡県遠賀郡水巻町下二西3-7-16",
    "prefecture": "福岡県",
    "robots_txt_status": "robots.txt なし(2026-10-20確認、404。禁止指定なし)",
    "source_note": "直営通販 organic-coffee.jp のカテゴリ「レギュラーコーヒー豆」と各商品ページを2026-10-20に確認。特商法(/view/contract)で所在地、公式 windfarm.co.jp/4rinen で自社焙煎(ご注文を受けてから焙煎)と直営店 珈琲工房ウインドファーム+(水巻町)を確認",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.organic-coffee.jp"
LIST_URL = BASE_URL + "/view/category/ct1"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2

EXCLUDE_TITLE_KEYWORDS = ("セット", "ドリップバッグ", "（粉）", "(粉)")
EXCLUDE_PAGE_KEYWORDS = ("生産地で焙煎したコーヒーを輸入",)  # タンナコーヒー(産地焙煎の輸入品)
ORIGIN_SPLIT = re.compile(r"[、,，・]")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_listing() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items = []
    seen = set()
    for li in soup.find_all("li"):
        name_p = li.select_one("p.item-name a")
        if not name_p:
            continue
        m = re.search(r"/view/item/(\d+)", name_p["href"])
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        price_p = li.select_one("p.price")
        price_m = re.match(r"\s*([\d,]+)", price_p.get_text()) if price_p else None
        origin_p = li.select_one("p.item-category")
        origin = re.sub(r"^原産地[：:]", "", origin_p.get_text(strip=True)) if origin_p else None
        items.append({
            "id": m.group(1),
            "title": name_p.get_text(strip=True),
            "sold_out": li.select_one("p.item-soldout") is not None,
            "price": int(price_m.group(1).replace(",", "")) if price_m else None,
            "origin": origin,
        })
    return items


def clean_name(title: str) -> str:
    t = unicodedata.normalize("NFKC", title)
    t = re.sub(r"【[^】]*(?:代替パッケージ|価格改定)[^】]*】", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def weight_from(title: str) -> int | None:
    t = unicodedata.normalize("NFKC", title)
    m = re.search(r"(\d+)\s*g", t, re.IGNORECASE)
    return int(m.group(1)) if m else None


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
        return None
    time.sleep(REQUEST_INTERVAL)
    page = fetch(f"{BASE_URL}/view/item/{item['id']}")
    if any(k in page for k in EXCLUDE_PAGE_KEYWORDS):
        print(f"[skip] 産地焙煎の輸入品のため除外: {title}")
        return None
    name = clean_name(title)
    weight = weight_from(title)
    page_text = re.sub(r"\s+", "", BeautifulSoup(page, "html.parser").get_text())
    roast = "深煎り" if ("深煎り焙煎になっています" in page_text or "焙煎度合いは深煎りです" in page_text) else None

    origins = [o.strip() for o in ORIGIN_SPLIT.split(item["origin"] or "") if o.strip()]
    parsed = parse_product(name)
    if len(origins) >= 2:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ブレンド" if "ブレンド" in name else "ストレート"
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            country = (detect_country_name(origins[0]) or origins[0]) if origins else None  # 「ネパール」「タイ」等は辞書に無いため店の原産地表記を採用
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "shop_attribute"
            else:
                parsed = apply_category_hint_fallback(parsed, name)
    in_stock = not item["sold_out"]
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
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": origins if len(origins) >= 2 else [],
        "price": item["price"],
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_listing():
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_windfarm.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_windfarm.json に出力しました")


if __name__ == "__main__":
    main()
