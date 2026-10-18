# -*- coding: utf-8 -*-
"""
scrape_mitikusacoffee.py

みちくさ COFFEE ROASTER & DAREKA COFFEE STAND(cafemitikusa.com、佐賀県佐賀市本庄町本庄167-11)の
商品情報を取得する。Shopify。

【店名について】
サイト上の表記は「みちくさコーヒーロースター」、特商法表記は「cafe みちくさ&コーヒーロースターズ」。
メディア(九州ウォーカー)では「みちくさ コーヒーロースター&ダレカ コーヒースタンド」。
登録名は依頼元指定の「みちくさ COFFEE ROASTER & DAREKA COFFEE STAND」を採用。

【住所】
特定商取引法に基づく表記(/policies/legal-notice)の所在地(〒840-0023 佐賀県佐賀市本庄町本庄167-11)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「コーヒー豆」の商品のみ。
定期便・ギフト・水出しパックは除外。ドリップパックはバリエーションの一つであり除外(「豆のまま」を採用)。
重量は商品本文の「内容量 ：150g」を優先し、無ければ「豆のまま」バリエーション名の「50g」を採用する。
焙煎度は本文の「焙煎度合い ：」から取得(無い商品はNone)。
"""

import json
import re

import requests

REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "みちくさ COFFEE ROASTER & DAREKA COFFEE STAND",
    "url": "https://cafemitikusa.com/",
    "platform": "Shopify",
    "address": "佐賀県佐賀市本庄町本庄167-11",
    "prefecture": "佐賀県",
    "robots_txt_status": "許可(Shopify標準。商品・コレクションはクロール可)",
}

BASE_URL = "https://cafemitikusa.com"
BEAN_TYPE = "コーヒー豆"
CONTENT_PATTERN = re.compile(r"内\s*容量\s*[：:]\s*(\d+)\s*[gｇ]")
VARIANT_WEIGHT = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"焙煎度合い\s*[：:]\s*([^\s　]+)")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "定期便" in title or "ギフト" in title or "セット" in title:
            continue

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)

        # 代表バリエーション: 「豆のまま」(先頭)
        variant = p["variants"][0]

        weight = None
        m = CONTENT_PATTERN.search(body)
        if m:
            weight = int(m.group(1))
        else:
            m = VARIANT_WEIGHT.search(variant.get("title") or "")
            if m:
                weight = int(m.group(1))

        roast = None
        m = ROAST_PATTERN.search(body)
        if m:
            roast = m.group(1)

        parsed = parse_product(title)
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
            if not parsed["origin_country"] and "中国" in title:
                # 辞書に「中国」単体が無い(「中国地方」との衝突回避)ため、店固有に補完する
                parsed["origin_country"] = "中国"
                parsed["origin_source"] = "raw_name"

        available = bool(variant.get("available"))
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": body[:400] or None,
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
    with open("data_mitikusacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mitikusacoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
