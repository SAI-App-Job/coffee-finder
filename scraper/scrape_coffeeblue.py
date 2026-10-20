# -*- coding: utf-8 -*-
"""
scrape_coffeeblue.py

COFFEE BLUE(https://coffeeblue.base.shop/、熊本県熊本市中央区出水1-4-27、店主 木下拓朗)の
商品情報を取得する。BASE。自家焙煎のスペシャルティコーヒー豆の店舗(Coffee Roastery & Shop)。

【店舗発見の経緯】
モール・独自EC発掘の試験調査(2026-10)。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全8商品のうち、コーヒー豆(シングルオリジン・
デカフェ)の6銘柄を対象とする。おすすめ3種セット、ドリップバッグは除外。
重量は商品名の表記(150g、デカフェのみ200g)を採用し、焙煎度・精製方法は
商品説明の「焙煎度:Light Roast(浅煎り)」等の表記から取る。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
User-agent: *はAllow: /(/cart/ /web_cart/ /shops/等のみDisallow)。python-requests/curl等は
個別にDisallowされているため、識別可能な独自User-Agentを使い、間隔は5秒以上空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "COFFEE BLUE",
    "url": "https://coffeeblue.base.shop/",
    "platform": "BASE",
    "address": "熊本県熊本市中央区出水1-4-27",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(User-agent: *でAllow: /。python-requests/curl等は個別禁止のため識別可能なUser-Agentで5秒間隔)",
    "source_note": "公式サイト(ABOUT・特商法)、ウォーカープラス https://www.walkerplus.com/article/1210008/ を2026-10-20に確認。商品はsitemap.xmlと各商品ページから2026-10-20に取得。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://coffeeblue.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g))
ITEMS = [
    ("148833322", "Brazil Rancho Sao Benedito Yellow Catucai Natural DR", 150),
    ("150937955", "Kenya New Joma Farm Washed", 150),
    ("154840084", "Ethiopia Haro Batume Drying station", 150),
    ("155557803", "Colombia Raul Duran Castillo Washed", 150),
    ("148177268", "Honduras Yerin Sagastume Pacas Washed", 150),
    ("95135748", "Mexico Chiapas Decaf", 200),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"焙煎度\s*[:：][^（(]*[（(]\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)\s*[）)]")
PROCESS_PATTERN = re.compile(r"生産処理\s*[:：]\s*([A-Za-z][A-Za-z ]*[A-Za-z])")


def build_record(item_id: str, name: str, weight_g: int) -> dict:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc_raw = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", desc_raw).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    roast_m = ROAST_PATTERN.search(desc_raw)
    roast_level = roast_m.group(1) if roast_m else None

    parsed = parse_product(name)
    detected = detect_country_name(name)
    if detected and not parsed["origin_country"]:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, name)
    process = parsed["processing_method"]
    if not process:
        pm = PROCESS_PATTERN.search(desc_raw)
        if pm:
            process = normalize_processing_method(pm.group(1).strip())

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": process,
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, (item_id, name, weight_g) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            records.append(build_record(item_id, name, weight_g))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeeblue.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeblue.json に出力しました")


if __name__ == "__main__":
    main()
