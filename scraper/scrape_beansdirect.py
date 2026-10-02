# -*- coding: utf-8 -*-
"""
scrape_beansdirect.py

自家焙煎珈琲豆専門店「ビーンズ」(beans-direct.com「ビーンズダイレクト」、埼玉県越谷市
蒲生寿町18-30、店主 古俣満。注文後に焙煎して発送する自家焙煎店)の商品情報を取得する。
CGIカート形式の静的HTMLサイト(Shift_JIS)。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): products.htmlの表(ブレンド豆6・ストレート豆約17)の
うち、HTMLコメントアウトされていない行を対象とする。表の価格は200g価格(200gから注文可、
500g以上は割引)のため200gを代表重量とする。注文欄が「欠品中」の行は完売として収録する。
焙煎度は商品ごとの記載がなく味の傾向別の並びのみのためroast_levelはNone。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ビーンズ(越谷)",
    "url": "http://www.beans-direct.com/",
    "platform": "独自サイト(CGIカート)",
    "address": "埼玉県越谷市蒲生寿町18-30",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

PRODUCTS_URL = "http://www.beans-direct.com/products.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 銘柄名から国名が判別できないもの(商品説明・一般的な銘柄の産地による)
ORIGIN_OVERRIDES = {
    "モカマタリNo.9": "イエメン",
    "トラジャ・カロシ": "インドネシア",
    "ニューギニア": "パプアニューギニア",
    "ガテマラSHB": "グアテマラ",
    "エメラルドマウンテン": "コロンビア",
    "ブルーマウンテンセレクト": "ジャマイカ",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(PRODUCTS_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "shift_jis"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3 or tr.find("table"):
            continue
        name = re.sub(r"\s+", " ", tds[0].get_text(strip=True)).lstrip("★").strip()
        price_m = re.search(r"[￥¥]\s*([\d,]+)", tds[1].get_text(strip=True))
        if not name or not price_m:
            continue
        desc = tds[2].get_text(strip=True) or None
        out_of_stock = "欠品" in tr.get_text()

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
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
            "price": int(price_m.group(1).replace(",", "")),
            "weight_g": 200,
            "stock_status": "完売" if out_of_stock else "販売中",
            "out_of_stock": out_of_stock,
            "product_url": f"{PRODUCTS_URL}#{quote(name)}",  # 全商品が同一ページのため、商品IDを一意にするフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beansdirect.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beansdirect.json に出力しました")


if __name__ == "__main__":
    main()
