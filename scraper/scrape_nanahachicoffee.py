# -*- coding: utf-8 -*-
"""
scrape_nanahachicoffee.py

78coffee(ナナハチコーヒー。埼玉県鴻巣市前砂のコーヒースタンド兼アンティーク雑貨店。
78coffee.shop-pro.jp、カラーミーショップ、charset=EUC-JP)の商品情報を取得する。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、2ページ)から、定期便・ドリップバッグ・ギフト・水出し珈琲
(パック)を除いた豆銘柄。商品ページは「コーヒー豆(粉)100gの商品です」と記載され、バリエーション選択肢は
無い(Colorme.product.variants が空)。豆のままか粉かの指定方法は商品ページ・特商法に記載が無く
不明(注文時の備考欄等と思われる)。価格は100gの内税価格。
【焙煎度】説明文に「中深焙りで…」「当店で一番深焙りの焙煎豆」と書かれた商品のみ取得。その他はnull。
【在庫】構造化された在庫情報なし。「SOLD OUT/品切れ」等の表記があれば品切れ。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "78coffee",
    "url": "http://78coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "埼玉県鴻巣市前砂427-10",
    "prefecture": "埼玉県",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "http://78coffee.shop-pro.jp/ の商品一覧・各商品ページ・特商法(?mode=sk)、公式 http://78coffee.mods.jp/ "
                   "(自家焙煎・店内喫茶スペース)を2026-10-26に確認。カラーミーの著作権表記は2026年で稼働中。"
                   "商品ページは「コーヒー豆(粉)100g」表記で豆/粉の選択方法は不明。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "http://78coffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
EXCLUDE_KEYWORDS = ("定期便", "ドリップバッグ", "ギフト", "水出し", "セット")
ROAST_PATTERN = re.compile(r"(中浅|中深|浅|中|深)焙り")
ROAST_MAP = {"中浅": "中浅煎り", "中深": "中深煎り", "浅": "浅煎り", "中": "中煎り", "深": "深煎り"}


def fetch(url: str) -> BeautifulSoup:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    items: dict[str, str] = {}
    for page in range(1, 6):
        soup = fetch(LIST_URL + ("" if page == 1 else f"&page={page}"))
        new = 0
        for a in soup.find_all("a", href=re.compile(r"^\?pid=\d+")):
            name = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            m = re.search(r"pid=(\d+)", a["href"])
            if not name or m.group(1) in items:
                continue
            items[m.group(1)] = name
            new += 1
        if new == 0:
            break
    return [{"pid": k, "name": v} for k, v in items.items()]


def build_record(item: dict) -> dict | None:
    url = f"{BASE_URL}?pid={item['pid']}"
    soup = fetch(url)
    title_el = soup.select_one("h2.product_name")
    title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)).strip() if title_el else item["name"]
    desc_el = soup.select_one("div.product_description")
    desc_lines = [l.strip() for l in desc_el.get_text("\n", strip=True).split("\n") if l.strip()] if desc_el else []
    desc = " ".join(desc_lines)
    if any(k in title for k in EXCLUDE_KEYWORDS) or "コーヒー豆" not in desc:
        return None

    price = None
    full = soup.get_text(" ", strip=True)
    pm = re.search(r"販売価格\s*([\d,]+)円", full)
    if pm:
        price = int(pm.group(1).replace(",", ""))
    wm = re.search(r"(\d+)\s*g", desc)
    weight = int(wm.group(1)) if wm else None

    rm = ROAST_PATTERN.search(desc)
    roast_level = ROAST_MAP[rm.group(1)] if rm else None

    parsed = parse_product(title)
    if "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if not c and "ケニヤ" in title:
                c = "ケニア"
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    flavor = " ".join(l for l in desc_lines if "100gの商品です" not in l) or None
    out_of_stock = bool(re.search(r"SOLD\s*OUT|売り切れ|在庫なし|品切れ|入荷待ち", full, re.I))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(k in item["name"] for k in EXCLUDE_KEYWORDS):
            continue
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_nanahachicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nanahachicoffee.json に出力しました")


if __name__ == "__main__":
    main()
