# -*- coding: utf-8 -*-
"""
scrape_42195coffee.py

42195 COFFEE(https://42195coffee.wixsite.com/toppage、大阪府大阪市北区中津3-12-15、
中津駅近くの自家焙煎コーヒー店)の焙煎豆小売通販の商品情報を取得する。Wix。

【店舗発見の経緯】
全国再調査(大阪府)の新規発掘で発見。

【取得方法について】
実データ確認済み(2026-10時点): 商品は公式サイトの「ONLINE SHOPPING」ページ
(/toppage/online-shopping)に静的テキストで掲載されており(カート機能なし。メール・
電話で希望の豆とグラム数を伝えて注文する方式)、サーバー側HTMLに含まれるため
通常のGETで取得できる。構造は
  セクション見出し(ブレンド/シングル)
  商品名 / 説明1行(焙煎度の記載を含むことがある) / 「100g NNN円」 / 「200g NNN円」
の繰り返し。「100g NNN円」の行の2行上を商品名とし、最小重量(100g)の価格を採用する。
連絡先: 公式サイトのCONTACTページに「大阪市北区中津3-12-15」の記載あり(住所確認済み)。

【在庫状況について】
在庫の表示はないため、掲載されている商品は販売中として扱う。

【robots.txtについて】
確認済み(2026-10時点): User-agent: * は Allow: /(lightbox用クエリのみDisallow)。
本スクレイパーは識別可能な独自User-Agentを使用する。

【product_urlについて】
全商品が1ページに載っているため、ページURLに商品名のフラグメント(#商品名)を付けて
商品ごとに一意にしている。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "42195 COFFEE",
    "url": "https://42195coffee.wixsite.com/toppage",
    "platform": "Wix",
    "address": "大阪府大阪市北区中津3-12-15",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10確認。User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
}

SHOP_PAGE_URL = "https://42195coffee.wixsite.com/toppage/online-shopping"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

PRICE_100G_PATTERN = re.compile(r"^100\s*g\s*([\d,]+)\s*円")
ROAST_PATTERN = re.compile(r"^(浅|中浅|中|中深|深)煎")
SECTION_NAMES = ("ブレンド", "シングル")


def fetch_lines() -> list[str]:
    resp = requests.get(SHOP_PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [re.sub(r"[​　\x00]+", " ", l).strip() for l in soup.get_text("\n").split("\n")]
    return [l for l in lines if l]


def parse_items(lines: list[str]) -> list[dict]:
    items = []
    section = None
    for i, line in enumerate(lines):
        if line in SECTION_NAMES:
            section = line
            continue
        m = PRICE_100G_PATTERN.match(line)
        if m and i >= 2:
            items.append({
                "name": lines[i - 2],
                "description": lines[i - 1],
                "price": int(m.group(1).replace(",", "")),
                "section": section,
            })
    return items


def build_record(item: dict) -> dict | None:
    name = item["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item["section"] == "ブレンド":
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
    elif not parsed["origin_country"]:
        detected = detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"

    roast = parsed["roast_level"]
    rm = ROAST_PATTERN.match(item["description"])
    if not roast and rm:
        roast = rm.group(1) + "煎り"

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
        "flavor_notes": item["description"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": 100,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{SHOP_PAGE_URL}#{urllib.parse.quote(name)}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_items(fetch_lines()):
        record = build_record(item)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_42195coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_42195coffee.json に出力しました")


if __name__ == "__main__":
    main()
