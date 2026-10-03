# -*- coding: utf-8 -*-
"""
scrape_beansoikos.py

BeansMart Oikos(https://www.beansoikos.co.jp/、神奈川県中郡大磯町大磯959)の商品情報を取得する。Shopify。

【店舗発見の経緯】
神奈川県の自家焙煎店調査(Kanagawa A)で発見。公式サイトの特定商取引法表記・LOCATIONページで
神奈川県中郡大磯町の所在地を、サイト説明文で自家焙煎(店舗は1店舗)を確認した。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`全24商品のうち、「豆のまま」バリエーションを
持つ焙煎豆(シングルオリジン・ブレンド・デカフェ)の14商品を対象とする。
コーヒーバッグ・リキッドコーヒー・お試し/おすすめ/ギフトセット・定期便・ギフトボックスは除外。
バリエーションは「<重量>g / <挽き方>」の組で200g/500gがあり、豆のままの最小重量(200g)の価格を代表とする。

【robots.txtについて】
Shopify標準構成(User-agent: * は Allow: /)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BeansMart Oikos",
    "url": "https://www.beansoikos.co.jp/",
    "platform": "Shopify",
    "address": "神奈川県中郡大磯町大磯959",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(Shopify標準構成。User-agent: * は Allow: /)",
}

BASE_URL = "https://www.beansoikos.co.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
BEANS_LABEL = "豆のまま"

# 商品名の国名が辞書で検出できないものの産地を明示する(商品説明文で確認済みのもの)
ORIGIN_OVERRIDES = {}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title or "バッグ" in title or "ギフト" in title or "リキッド" in title:
            continue

        # 「豆のまま」バリエーションのうち最小重量のものを代表とする
        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and BEANS_LABEL in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if parsed["is_flavored"]:
            continue
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if title in ORIGIN_OVERRIDES and not parsed["origin_country"]:
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
    with open("data_beansoikos.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beansoikos.json に出力しました")


if __name__ == "__main__":
    main()
