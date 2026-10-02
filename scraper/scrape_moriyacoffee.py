# -*- coding: utf-8 -*-
"""
scrape_moriyacoffee.py

森谷珈琲工房(moriyacoffee.ocnk.net、埼玉県さいたま市岩槻区慈恩寺546-28、
2016年開業、夫婦経営の自家焙煎コーヒー豆屋)の商品情報を取得する。
おちゃのこネット。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「現在取扱焙煎豆」カテゴリ(category 2)の21件のうち、
ドリップパックを除いた20件は、同一銘柄が100g/200gの別商品ページとして登録
されているため、他店舗と同様に最小の代表重量(100g)のみを収録する(10銘柄)。
ブレンド(オリジナルブレンド極・パナマブレンド・パナマ魔女の森ブレンド・
タンザニアブレンド)はブレンド、他は単一産地のストレート。

【ページ構造について】
実データ確認済み: 販売価格は本文の「販売価格 : 1,150 円」、在庫は「在庫なし」の
有無、説明はog:description(精製方法・ロースターコメント・焙煎度合い)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "森谷珈琲工房",
    "url": "https://moriyacoffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "埼玉県さいたま市岩槻区慈恩寺546-28",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://moriyacoffee.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_URL = f"{BASE_URL}/product-list/2"

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r"販売価格\s*:\s*([\d,]+)\s*円")
ROAST_PATTERN = re.compile(r"焙煎度合い:\s*([^\s]+)")
WEIGHT_PATTERN = re.compile(r"([0-9０-９]+)\s*[gｇ]")


def to_int(text: str) -> int:
    return int(text.translate(str.maketrans("０１２３４５６７８９", "0123456789")))


def build_record(pid: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/product/{pid}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    raw_title = re.sub(r"\s+", " ", title_m.group(1)).strip()
    if "ドリップパック" in raw_title:
        return None
    weight_m = WEIGHT_PATTERN.search(raw_title)
    if not weight_m or to_int(weight_m.group(1)) != 100:
        return None

    page_text = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
    price_m = PRICE_PATTERN.search(page_text)
    out_of_stock = "在庫なし" in page_text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else None
    roast_m = ROAST_PATTERN.search(desc or "")

    name = re.sub(r"\s*[0-9０-９]+\s*[gｇ]\s*", " ", raw_title)
    name = re.sub(r"[（(]ハイロースト[)）]", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    parsed = parse_product(name)
    if "ブレンド" in name or "極" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name) or detect_country_name(raw_title)
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
        "roast_level": roast_m.group(1) if roast_m else parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "weight_g": 100,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": f"{BASE_URL}/product/{pid}",
    }


def scrape_all_products() -> list[dict]:
    resp = requests.get(CATEGORY_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    pids = list(dict.fromkeys(re.findall(r"/product/(\d+)", resp.text)))
    records = []
    for pid in pids:
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {pid} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_moriyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_moriyacoffee.json に出力しました")


if __name__ == "__main__":
    main()
