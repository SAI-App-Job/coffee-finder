# -*- coding: utf-8 -*-
"""
scrape_kyotogreatcoffee.py

京都グレートコーヒー(https://kyoto-greatcoffee.com/、京都府京都市左京区田中里ノ内町42)の商品情報を取得する。
Shopify(/products.json)。

【対象商品について】
実データ確認済み(2026-10-21): 全18商品のうち、「ゴールデンブレンドとお好きなコーヒー豆の2種セット」
(オンライン販売限定のセット)を除く17銘柄(シングルオリジン8・ブレンド9)を対象とする。
バリエーションは「重量 / 挽き方」(0.3kg〜5kg、豆のまま・細挽き・中挽き・粗挽き・豆・挽き両方)で、
「豆のまま」の最小重量の価格を代表とする(多くは300g、グレートブレンド・深煎りビターブレンド・
ゴールデンブレンドは500gが最小)。量り売りで、重量が増えるほど割引になる価格体系。
"""

import json
import os
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "京都グレートコーヒー",
    "url": "https://kyoto-greatcoffee.com/",
    "platform": "Shopify",
    "address": "京都府京都市左京区田中里ノ内町42",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10-21確認。Shopify標準のrobots.txtで/products.jsonは禁止されていない)",
    "source_note": "公式Shopify https://kyoto-greatcoffee.com/products.json を2026-10-21に確認。住所は /policies/legal-notice の所在地(〒606-8212)。トップに「世界各国から取り寄せたコーヒー豆を毎日焙煎」(自家焙煎の明記は無く、毎日焙煎の記述が根拠)。店舗案内あり(営業10:00-18:00、土日祝定休)、食べログ掲載。商品最終更新2026-10-21",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://kyoto-greatcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
KG_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.I)

EXCLUDE_HANDLES = {"選べる2種のコーヒー豆セット"}

# 商品名に「ブレンド」を含まないがブレンドの商品
BLEND_TITLES = {"グレートGX", "グレート87", "スペシャルアイス"}

# 説明文に焙煎度の記載があるもの
ROAST_OVERRIDES = {
    "深煎りビターブレンド": "深煎り",
    "スペシャルアイス": "フレンチロースト",     # 説明「フレンチローストで仕上げ」
    "スペシャルブレンド": "シティロースト",      # 説明「シティローストで仕上げた中南米産の豆」
}

ORIGIN_OVERRIDES = {"キリマンジャロ": "タンザニア", "モカ": "エチオピア"}


def load_products() -> list[dict]:
    # 環境変数 PRODUCTS_JSON_FILE が指定されていれば、事前に取得済みの /products.json を読む
    # (サイト側が429を返し続ける場合に、過去に取得したスナップショットから生成するため)
    snapshot = os.environ.get("PRODUCTS_JSON_FILE")
    if snapshot:
        with open(snapshot, encoding="utf-8") as f:
            return json.load(f).get("products", [])
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("products", [])


def scrape_all_products() -> list[dict]:
    records = []
    for p in load_products():
        if p["handle"] in EXCLUDE_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            vt = unicodedata.normalize("NFKC", v.get("title") or "")
            m = KG_PATTERN.search(vt)
            if m and "豆のまま" in vt:
                weighted.append((round(float(m.group(1)) * 1000), v))
        if not weighted:
            print(f"[skip] 豆のまま・重量のバリエーションなし: {p['handle']}")
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if title in BLEND_TITLES:
            parsed["category"] = "ブレンド"
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if title in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[title]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": ROAST_OVERRIDES.get(title) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kyotogreatcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kyotogreatcoffee.json に出力しました")


if __name__ == "__main__":
    main()
