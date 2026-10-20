# -*- coding: utf-8 -*-
"""
scrape_andcoffeeroasters.py

AND COFFEE ROASTERS(https://www.andcoffeeroasters.com/、熊本県熊本市中央区上通町11-22 BRビル、
2013年開業の自家焙煎スペシャルティコーヒー店)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
モール・独自EC発掘の試験調査(2026-10)。店舗は熊本県内に3店舗(AND COFFEE BREWERS)と
東京・日比谷に1店舗。11店舗未満のため登録対象。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全36商品のうち、コーヒー豆(シングルオリジン・
デカフェ)の14銘柄を対象とする。次は除外: インフューズド(COLOMBIA QUINDIO INFUSED PEACH)、
大容量1kg(200g×5袋)、ドリップバッグ、コールドブリューバッグ、お試しセット、定期便、器具。
各銘柄の重量(100g/150g)は商品名の表記を採用する(豆/粉のバリエーションは同額)。
焙煎度は商品名末尾の[LIGHT ROAST]等から決める。
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
    "name": "AND COFFEE ROASTERS",
    "url": "https://www.andcoffeeroasters.com/",
    "platform": "BASE",
    "address": "熊本県熊本市中央区上通町11-22 BRビル",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(User-agent: *でAllow: /。python-requests/curl等は個別禁止のため識別可能なUser-Agentで5秒間隔)",
    "source_note": "公式サイト(ABOUT・特商法)、ウォーカープラス https://www.walkerplus.com/trend/matome/article/1087953/ を2026-10-20に確認。商品はsitemap.xmlと各商品ページから2026-10-20に取得。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.andcoffeeroasters.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 焙煎度)
ITEMS = [
    ("161660562", "ETHIOPIA SIDAMA BENSA BOMBE", 150, "浅煎り"),
    ("142340017", "COLOMBIA EL DIVISO BOURBON AJI", 100, "浅煎り"),
    ("142773149", "COLOMBIA EL ORIGEN PAPAYO", 100, "浅煎り"),
    ("158480988", "COLOMBIA CGLE THREE DRAGONS", 100, "浅煎り"),
    ("144242756", "NICARAGUA LA HUELLA", 100, "浅煎り"),
    ("149331952", "PERU DAVID FLORES GEISHA", 100, "浅煎り"),
    ("142537975", "BURUNDI KAYAVE WASHED", 150, "浅煎り"),
    ("149330543", "BURUNDI KARAMBO WS NATURAL", 150, "浅煎り"),
    ("151755633", "KENYA TEGU FACTORY", 150, "浅煎り"),
    ("155148381", "TANZANIA ACACIA HILLS KENT", 150, "浅煎り"),
    ("156690618", "HONDURAS LOS ROBLES SL28", 150, "浅煎り"),
    ("155146973", "RWANDA KARISIMBI MOUNTAIN", 150, "中煎り"),
    ("158480870", "RWANDA DUKUNDE KAWA NKARA", 150, "浅煎り"),
    ("118484817", "ETHIOPIA SIDAMO DECAF デカフェ", 150, "中深煎り"),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_PATTERN = re.compile(r"精製方法\s*[:：]\s*([A-Za-z][A-Za-z ]*[A-Za-z])")


def build_record(item_id: str, name: str, weight_g: int, roast_level: str) -> dict:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc_raw = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    desc_raw = desc_raw.split("____")[0]  # 発送に関する定型文より前だけを使う
    desc = re.sub(r"\s+", " ", desc_raw).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

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
        "roast_level": roast_level,
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
    for i, (item_id, name, weight_g, roast_level) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            records.append(build_record(item_id, name, weight_g, roast_level))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_andcoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_andcoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
