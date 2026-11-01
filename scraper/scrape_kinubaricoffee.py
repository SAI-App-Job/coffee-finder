# -*- coding: utf-8 -*-
"""
scrape_kinubaricoffee.py

KINUBARI COFFEE ROASTERS(https://shop.kinubaricoffee.com/、北海道上川郡上川町南町1058)の商品情報を取得する。BASE。

【店舗発見の経緯】
北海道の未登録・自家焙煎店の発掘調査(2026-10-26)で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全17商品のうち自家焙煎コーヒー豆8銘柄(季節ブレンドMera2026、シングル6、デカフェ1)。豆/粉の選択あり(豆のまま基準)。通常は150g、デカフェのみ100g。お試し3種セット・ドリップバッグ・定期便・ギフト・グッズは除外。焙煎度は商品説明の「焙煎度合」から取得。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
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
    "name": "KINUBARI COFFEE ROASTERS",
    "url": "https://shop.kinubaricoffee.com/",
    "platform": "BASE",
    "address": "北海道上川郡上川町南町1058",
    "prefecture": "北海道",
    "source_note": "BASEショップ(https://shop.kinubaricoffee.com/)のabout・サイトマップ・各商品ページを2026-10-26に確認。住所は公式BASEショップのトップページ記載(〒078-1753 上川町南町1058)",
    "last_verified_at": "2026-10-26",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.kinubaricoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('155940966', 'AUTUMN BLEND Mera 2026【期間限定】', 150, 'ブレンド', '中深煎り'),
    ('127824018', 'Indonesia Natural', 150, None, '中煎り'),
    ('28891391', 'Rwanda Natural', 150, None, '中深煎り'),
    ('68792473', 'Ethiopia Natural', 150, None, '中深煎り'),
    ('68792598', 'Guatemala Natural', 150, None, '中深煎り'),
    ('67281245', 'Costa Rica Anaerobic Honey', 150, None, '中深煎り'),
    ('68791157', 'Brazil Natural', 150, None, '中深煎り'),
    ('128263750', '【Decaf】Ethiopia Natural', 100, 'デカフェ', '中深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    time.sleep(5)  # BASE: リクエスト間隔5秒以上
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
    with open("data_kinubaricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kinubaricoffee.json に出力しました")


if __name__ == "__main__":
    main()
