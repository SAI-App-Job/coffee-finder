# -*- coding: utf-8 -*-
"""
scrape_daisycoffee.py

DAISY COFFEE(デイジーコーヒー、daisycoffee.base.shop、静岡県焼津市本町2-13-28、手焼き自家焙煎の
コーヒー店)の商品情報を取得する。BASE。

【店舗発見の経緯】
静岡県の再調査の新規発掘で発見。住所は販売ページの特定商取引法表記(/law)に番地まで記載。

【対象商品について】
実データ確認済み(2026-10時点): BASE全9商品(/items/all)のうち、自家焙煎のコーヒー豆9銘柄
(シングル5・ブレンド4。各200g)すべて。ドリップ/水出しパック・ギフト・セットの商品は一覧にない。
商品名・分類・焙煎度・産地は、商品ページの説明文(「深煎のブラジル」「オリジナルブレンドのシーサイド」等)を
確認したうえで下のITEMSに明示している(商品名が英語表記・「Columbia」等の綴り違いのため)。
焙煎度が「中深煎中煎」のように複数併記のブレンド(デイジーズ・シーサイド)はNone。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
購入時に「豆/粉」を選択でき、豆のまま在庫がある場合は販売中とする(partially_purchasableも販売中)。

【robots.txtについて】
実データ確認済み(2026-10-26): 他のBASE系店舗と同一の記述(User-agent: *では許可、/cart/等のみ禁止)。
識別可能な独自User-Agentを使用し、リクエスト間隔は5秒。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "DAISY COFFEE",
    "url": "https://daisycoffee.base.shop/",
    "platform": "BASE",
    "address": "静岡県焼津市本町2-13-28",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://daisycoffee.base.shop/items/all)の全9商品と各商品ページを2026-10-26に確認。住所は同店の特定商取引法表記 https://daisycoffee.base.shop/law (〒425-0022)。新着日付の記載がなく更新の新しさは不明。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://daisycoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.0

# (商品ID, 商品名, 分類, 焙煎度, 産地)
ITEMS = [
    ('28066378', 'Freshmocha.Irugachefu', 'ストレート', '浅煎り', 'エチオピア'),
    ('9202250', 'Tanzania.Feel', 'ストレート', '中煎り', 'タンザニア'),
    ('9202166', 'Columbia.Mild bitter', 'ストレート', '中深煎り', 'コロンビア'),
    ('28116050', 'Brazil Bitter choco', 'ストレート', '深煎り', 'ブラジル'),
    ('9198659', 'Manderin.French', 'ストレート', '深煎り', 'インドネシア'),
    ('12786929', 'Daisys', 'ブレンド', None, None),
    ('12787100', 'Seaside', 'ブレンド', None, None),
    ('12787188', 'Seagull', 'ブレンド', '中深煎り', None),
    ('12787168', 'Under the sea', 'ブレンド', '深煎り', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, category: str, roast_level: str | None, origin: str | None) -> dict:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    text = resp.text
    desc_m = DESC_PATTERN.search(text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(text)
    pur_m = PURCHASABILITY_PATTERN.search(text)
    sold_out = bool(pur_m) and pur_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    parsed["category"] = category
    if category == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "description"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": None,
        "processing_method": None,
        "grade": None,
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": [],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": 200,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, category, roast_level, origin in ITEMS:
        try:
            records.append(build_record(item_id, name, category, roast_level, origin))
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_daisycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_daisycoffee.json に出力しました")


if __name__ == "__main__":
    main()
