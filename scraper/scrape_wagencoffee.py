# -*- coding: utf-8 -*-
"""
scrape_wagencoffee.py

珈琲工房わげん(千葉県佐倉市栄町19-5、coffee-wagen.com。2003年開店の自家焙煎珈琲店、京成佐倉駅南口、
メール・FAX・電話注文で全国発送)の商品情報を取得する。静的HTMLサイト(Shift_JIS、HTTPのみ)の
「ビーンズガイド」(guide.html)に、品名・100g価格・コメント・味の4段階評価が並ぶ。

【対象商品について】
実データ確認済み(2026-10時点、guide.htmlの最終更新2026-05-04): ブレンド4・ストレート8の計12銘柄。
「ネット限定メニュー ブレンド4種お試しセット」はセット商品のため除外。
価格表記は「100g/円」のみで税込・税抜の別は記載なし(表記の数値をそのまま採用)。
全て100g価格を代表重量・価格とする。在庫表示・焙煎度の記載は無い。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲工房わげん",
    "url": "http://coffee-wagen.com/",
    "platform": "静的HTML(メール・FAX・電話注文)",
    "address": "千葉県佐倉市栄町19-5",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

GUIDE_URL = "http://coffee-wagen.com/guide.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ORIGIN_OVERRIDES = {
    "モカ マタリ": "イエメン",
    "モカ　マタリ": "イエメン",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(GUIDE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "shift_jis"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for a in soup.select("p.a"):
        name = re.sub(r"[\s　]+", " ", a.get_text(strip=True)).strip()
        b = a.find_next_sibling("p", class_="b")
        c = a.find_next_sibling("p", class_="c")
        if not name or name.replace(" ", "") == "品名" or not b:
            continue
        pm = re.search(r"(\d[\d,]*)", b.get_text())
        if not pm:
            continue
        desc = c.get_text(" ", strip=True) if c else None

        parsed = parse_product(name)
        if name.startswith("ブレンド") or "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            override = ORIGIN_OVERRIDES.get(name)
            detected = override or detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(pm.group(1).replace(",", "")),
            "weight_g": 100,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{GUIDE_URL}#{quote(name)}",  # 全商品が同一ページのため、商品IDを一意にするフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_wagencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wagencoffee.json に出力しました")


if __name__ == "__main__":
    main()
