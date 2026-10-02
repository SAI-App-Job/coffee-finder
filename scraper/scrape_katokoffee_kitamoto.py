# -*- coding: utf-8 -*-
"""
scrape_katokoffee_kitamoto.py

加藤珈琲(www.kato-coffee.com、埼玉県北本市本宿5-129、2003年開業、注文後の
直火自家焙煎)の商品情報を取得する。静的HTML+注文フォーム(order.php)。
※名古屋の「加藤珈琲店」とは別の店舗。既存の`scrape_katocoffee.py`
(別店舗)とは無関係なので、ファイル名にkitamotoを付けて区別している。

【店舗発見の経緯】
2026-09-04の別セッションで「独自EC(order.php)の構造調査に時間を要する」として
見送られていたが、全国再調査(埼玉県)で再検証し、商品ページが規則的な
静的HTMLであることを確認して実装した。

【対象商品について】
実データ確認済み(2026-10時点、更新日2026/9/30): ブレンド・アジア/アフリカ・
中南米ストレート1/2・カフェインレスの計5ページ。各商品は「商品番号：NNN」
で始まるブロックで、価格の代わりに「終売」「販売終了」と表示されている商品は
現在購入できないため除外する。各商品は焙煎度(ミディアム/シティ/
フルシティ/フレンチ)を注文時に選べるため、roast_levelは固定せず
roast_hintに選択可能な焙煎度を記録する。重量は200g(フレンチのみ約190g)。

【ページ構造について】
実データ確認済み: テキスト化した各ブロックは「商品番号→商品名(1〜2行)→
(豆・粉 中挽き)等の種別行→価格→200g→味の系統→焙煎度→説明」の順。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "加藤珈琲(北本)",
    "url": "https://www.kato-coffee.com/",
    "platform": "自社サイト(静的HTML+注文フォーム)",
    "address": "埼玉県北本市本宿5-129",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.kato-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

PAGES = ["blend.html", "asia_africa.html", "central_south_america1.html", "central_south_america2.html", "decafeh.html"]

TYPE_LINE = re.compile(r"^(ブレンド)?[（(].*(豆|粉)")
PRICE_LINE = re.compile(r"^(\d[\d,]*)円$")
OPTION_LINE = re.compile(r"^([（(]Ｍ[)）])?((ミディアム|シティ|フルシティ|フレンチ)[、,]?)+$")


def parse_page(page: str) -> list[dict]:
    resp = requests.get(f"{BASE_URL}/{page}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    text = BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True)
    text = text.split("『豆の特徴は")[0]
    blocks = text.split("商品番号：")[1:]

    records = []
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        number = lines[0]
        body = lines[1:]
        type_idx = next((i for i, ln in enumerate(body) if TYPE_LINE.match(ln)), None)
        if type_idx is None:
            continue
        name_lines = body[:type_idx]
        if body[type_idx].startswith("ブレンド"):
            name_lines = name_lines + ["ブレンド"]
        name = " ".join(name_lines)

        rest = body[type_idx + 1:]
        price = None
        discontinued = False
        for ln in rest[:3]:
            m = PRICE_LINE.match(ln)
            if m:
                price = int(m.group(1).replace(",", ""))
                break
            if ln in ("終売", "販売終了"):
                discontinued = True
                break
        if discontinued or price is None:
            continue

        option_lines = []
        desc_lines = []
        for ln in rest:
            if PRICE_LINE.match(ln) or ln == "200g":
                continue
            if OPTION_LINE.match(ln):
                option_lines.append(ln)
            else:
                desc_lines.append(ln)
        desc = " ".join(desc_lines).split(" 『")[0].strip() or None

        records.append({
            "number": number,
            "name": name,
            "price": price,
            "roast_hint": "".join(option_lines).strip("、") or None,
            "desc": desc,
            "page": page,
        })
    return records


def build_record(item: dict) -> dict:
    name = item["name"]
    parsed = parse_product(name)
    if item["page"] == "blend.html" or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": f"注文時に選択可: {item['roast_hint']}" if item["roast_hint"] else None,
        "flavor_notes": item["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": 200,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{BASE_URL}/{item['page']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    seen = set()
    for page in PAGES:
        for item in parse_page(page):
            if item["number"] in seen:
                continue
            seen.add(item["number"])
            records.append(build_record(item))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_katokoffee_kitamoto.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_katokoffee_kitamoto.json に出力しました")


if __name__ == "__main__":
    main()
