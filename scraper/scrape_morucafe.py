# -*- coding: utf-8 -*-
"""
scrape_morucafe.py

モルカフェ ~FARMERS PASSION~(珈琲農園直営店、愛知県豊川市東豊町5-22、株式会社SHANTI SHANTI
COFFEE FARM。ネパール・シャンジャ郡の自社農園産の豆を店頭で焙煎)の商品情報を取得する。
BASE(nepalcoffee.base.shop)。

【対象商品について】
実データ確認済み(2026-10-20、sitemap.xmlの全90商品ページを確認): コーヒー豆の単品は
ネパール産1種類を「精製×焙煎度」の組み合わせで5つ(ナチュラル×ライト/ウォッシュド×アメリカン/
ハニー×ミディアム/エイジング×ダーク/エイジング×ストロング)に分けたもので、それぞれ
150g/250g/500g/1kgの重量違いが別商品として並ぶ。最小重量の150gを代表とし、250g以上は
重複させない。除外: ギフト・お試しセット(各50g/100g)・定期便・ドリップパック・コーラ/カフェオレ
ベース・スパイス・ティー・雑貨。
商品名は商品ページの表記に産地「ネパール」を補っている。価格・在庫(item_purchasability)・
説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "モルカフェ ~FARMERS PASSION~",
    "url": "https://nepalcoffee.base.shop/",
    "platform": "BASE",
    "address": "愛知県豊川市東豊町5-22",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://nepalcoffee.base.shop/ の商品ページ(2026-10-20取得)。店舗は食べログ「珈琲農園直営店 mol cafe」(店頭で焙煎を行い)と公式 https://farmers-passion.com/ で確認。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://nepalcoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.5

# (商品ID, 商品名, 重量(g), 焙煎度, 焙煎度の原表記)
ITEMS = [
    ("99080303", "ネパール ナチュラル×ライト(極浅煎り)", 150, "浅煎り", "極浅煎り(ライトロースト)"),
    ("99080308", "ネパール ウォッシュド×アメリカン(浅煎り)", 150, "浅煎り", "浅煎り(アメリカン)"),
    ("99080309", "ネパール ハニー×ミディアム(中煎り)", 150, "中煎り", "中煎り(ミディアムロースト)"),
    ("99080311", "ネパール エイジング×ダーク(深煎り)", 150, "深煎り", "深煎り(ダークロースト)"),
    ("99080313", "ネパール エイジング×ストロング(極深煎り)", 150, "極深煎り", "極深煎り(ストロング)"),
]
PROCESS_OVERRIDES = {
    "99080311": "エイジング",
    "99080313": "エイジング",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, roast_level: str, roast_hint: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        import html as ihtml
        d = ihtml.unescape(desc_m.group(1))
        d = re.split(r"◆こんな方|【精製と焙煎】", d)[0]
        desc = re.sub(r"\s+", " ", d).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    process = PROCESS_OVERRIDES.get(item_id) or parsed["processing_method"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": "ストレート",
        "origin_country": "ネパール",
        "origin_source": "raw_name",
        "designated_brand": parsed["designated_brand"],
        "processing_method": process,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
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
    for i, (item_id, name, weight_g, roast_level, roast_hint) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            record = build_record(item_id, name, weight_g, roast_level, roast_hint)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_morucafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_morucafe.json に出力しました")


if __name__ == "__main__":
    main()
