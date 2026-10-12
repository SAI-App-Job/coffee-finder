# -*- coding: utf-8 -*-
"""
scrape_mamenokiishikawa.py

手作りコーヒー 豆の樹(金沢)(coffee-mamenoki.myshopify.com、石川県金沢市三馬3-195、
特定商取引法表記の事業者の所在地で確認、事業者名「豆の樹 川村正志」)の商品情報を取得する。
Shopify。福岡県の「豆の樹」(scrape_mamenoki.py)とは別店舗のため、slugを
mamenokiishikawaとし、店名に「(金沢)」を付けて区別する。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち生豆・焙煎豆の商品。
アイスコーヒー(液体)・カフェオレベース・おすすめセットは除外。
重量は商品名の「200g」等の表記から取得(表記が無いドミニカ タニー農園はnull)。
バリエーションは「豆のまま/粉」等の挽き方違いで価格は同一のため、豆の方を代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "手作りコーヒー 豆の樹(金沢)",
    "url": "https://coffee-mamenoki.myshopify.com/",
    "platform": "Shopify",
    "address": "石川県金沢市三馬3丁目195",
    "prefecture": "石川県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://coffee-mamenoki.myshopify.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_PATTERN = re.compile(r"(?<!限定\d\d)セット|リットル|カフェオレ|アイスコーヒー\s*\d+本|\d+本")
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.I)

# 商品名だけでは分類・産地を判定できない商品の補正(product id → 上書き値)
CATEGORY_OVERRIDES = {"19": "ストレート"}  # 「ブルマンブレンドみたいな味」はブレンドではない
ORIGIN_OVERRIDES = {
    "19": "ドミニカ共和国",
    "75": "インドネシア",   # ガヨマウンテン(スマトラ・アチェ)
    "11": "インドネシア",   # スマトラタイガー
    "46": "インドネシア",
    "65": "東ティモール",
    "85": "エチオピア",     # 「モカ」=エチオピア産(モカ・ギャルソ農園、カフェインレス)
    "34": "エチオピア",     # モカ・クジ・ウンガ農園
}


def parse_weight(title: str):
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    val = float(m.group(1))
    return int(val * 1000) if m.group(2).lower() == "kg" else int(val)


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != "コーヒー":
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if EXCLUDE_PATTERN.search(title):
            continue
        weight = parse_weight(title)

        # 先頭の「豆」系バリエーション(無ければ先頭)を代表とする
        variants = p["variants"]
        variant = next((v for v in variants if v["title"].startswith("豆") or v["title"] == "Default Title"), variants[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        pid = p["handle"]  # handleは商品ID(数値文字列)
        parsed = parse_product(title)
        if pid in CATEGORY_OVERRIDES:
            parsed["category"] = CATEGORY_OVERRIDES[pid]
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if pid in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
                parsed["origin_source"] = "raw_name"
        if "カフェインレス" in title and "デカフェ" not in parsed["post_processing_tags"]:
            parsed["post_processing_tags"].append("デカフェ")

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
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
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamenokiishikawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamenokiishikawa.json に出力しました")


if __name__ == "__main__":
    main()
