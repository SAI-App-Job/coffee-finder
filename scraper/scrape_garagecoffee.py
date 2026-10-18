# -*- coding: utf-8 -*-
"""
scrape_garagecoffee.py

GARAGE COFFEE(https://garagecoffee.official.ec/、宮崎県宮崎市広島2-6-14 中川ビル)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(宮崎県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xml/トップの18商品のうち、100gの豆11種(シングル5・ジャマイカ・デカフェ・ブレンド4)のみ対象。
ドリップバッグ(単品・4種セット・焼き菓子セット)・カフェオレベースは除外。
住所はBASE特商法の1号店(宮崎市広島2-6-14 中川ビル)。公式ABOUTには焙煎所「GARAGE COFFEE ROASTERY」
(宮崎市塩路1690-9)も記載があるが、オンライン販売豆の焙煎場所が焙煎所と確認できないため
特商法の所在地を採用。焙煎度は商品説明に明記のあるもの(LIGHT=中煎り、DARK・ジャマイカ=深煎り)のみ設定
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルに重量が付記されているため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GARAGE COFFEE",
    "url": "https://garagecoffee.official.ec/",
    "platform": "BASE",
    "address": "宮崎県宮崎市広島2-6-14 中川ビル",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://garagecoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("161150116", "HONDURAS SANTA LUCIA CASONA GEISHA WASHED", 100, None, None),
    ("155745770", "COSTARICA BURMAS DON JOSE GEISHA RED HONEY", 100, None, None),
    ("155745107", "ETHIOPIA MORKE NATURAL", 100, None, None),
    ("154264156", "ETHIOPIA BENCH MAJI G1 GESHA KARMACHI NATURAL", 100, None, None),
    ("142796677", "NICARAGUA LAS DELICIAS ANAEROBIC AT LOW TEMPERATURE", 100, None, None),
    ("102736278", "JAMAICA BLUE MOUNTAIN NO.1 WASHED", 100, None, "深煎り"),
    ("74085019", "ETHIOPIA DECAF", 100, "デカフェ", None),
    ("138507059", "SURF BLEND", 100, "ブレンド", None),
    ("67398017", "HINATA BLEND", 100, "ブレンド", None),
    ("66787086", "LIGHT BLEND", 100, "ブレンド", "中煎り"),
    ("67397945", "DARK BLEND", 100, "ブレンド", "深煎り"),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {
    "161150116": "ホンジュラス",
    "155745770": "コスタリカ",
    "155745107": "エチオピア",
    "154264156": "エチオピア",
    "142796677": "ニカラグア",
    "102736278": "ジャマイカ",
    "74085019": "エチオピア",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
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
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        time.sleep(1)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_garagecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_garagecoffee.json に出力しました")


if __name__ == "__main__":
    main()
