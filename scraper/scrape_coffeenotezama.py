# -*- coding: utf-8 -*-
"""
scrape_coffeenotezama.py

コーヒーノート(https://coffeenote.net/、神奈川県座間市入谷東4丁目53-20)の商品情報を取得する。Shopify。

【店舗発見の経緯】
神奈川県の自家焙煎店調査(Kanagawa A)で発見。公式サイトの特定商取引法表記で神奈川県座間市の
所在地を、トップページの説明で店内の焙煎機「ブタ釜」による自家焙煎を確認した(店舗は1店舗)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`全54商品のうち、「豆のまま」バリエーションを
持つ焙煎豆のみ(シングルオリジン・ブタ釜ブレンド・デカフェ・ブルーマウンテン/ハワイコナ)の15商品を対象とする。
コーヒーバッグ・ドリップバッグ・水出しパック・ザマオーレ(液体)・アイス・器具・セット類は除外。
バリエーションは「<重量>g / 豆のまま|粉に挽く」の組で、豆のままの最小重量
(ハワイコナ/ブルーマウンテンは100g、その他は200g)の価格を代表とする。
価格改定(令和8年7月1日)後の現行価格を取得している。

【robots.txtについて】
Shopify標準構成(User-agent: * は Allow: /)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "コーヒーノート",
    "url": "https://coffeenote.net/",
    "platform": "Shopify",
    "address": "神奈川県座間市入谷東4丁目53-20",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(Shopify標準構成。User-agent: * は Allow: /)",
}

BASE_URL = "https://coffeenote.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
BEANS_LABEL = "豆のまま"

# 商品名に国名が無い・辞書で検出できないものの産地を明示する(商品説明文で確認済みのもの)
ORIGIN_OVERRIDES = {
    "キリマンジャロ": "タンザニア",
    "アビシニアンモカ ワイニー": "エチオピア",    # 商品説明に「エチオピア産(アビシニアは古い呼び名)」とある
    "アビシニアンモカ シトリック": "エチオピア",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title or "バッグ" in title or "ドリップ" in title:
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
    with open("data_coffeenotezama.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeenotezama.json に出力しました")


if __name__ == "__main__":
    main()
