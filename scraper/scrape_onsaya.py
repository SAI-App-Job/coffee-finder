# -*- coding: utf-8 -*-
"""
scrape_onsaya.py

ONSAYA COFFEE(onsaya.com、岡山県岡山市北区奉還町2-9-1 が奉還町本店。岡山市内にほか3店)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちタグに「コーヒー豆」を持ち、
product_typeがSINGLE(シングルオリジン)またはBLEND(ブレンド)の商品を対象とする
(SET・GIFT・ドリップバッグ・器具・Tシャツ等は除外)。
バリエーションは「挽き目 / 豆の量 / 配送方法」の組で、「豆のまま」かつ最小重量(100g)の
バリエーションの価格を代表とする。焙煎度は商品説明の表記(浅煎り・中煎り・深煎り)から取る。
なおタグに「デカフェ」が付いているKENYA Gatinaは、説明文にデカフェの記載がなく
タグの誤設定と判断し、通常のストレートとして扱う。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "ONSAYA COFFEE",
    "url": "https://onsaya.com/",
    "platform": "Shopify",
    "address": "岡山県岡山市北区奉還町2-9-1",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(Shopify標準のrobots.txt。商品・コレクションのHTMLはクロール可と明記)",
}

BASE_URL = "https://onsaya.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TAG = "コーヒー豆"
BEAN_TYPES = {"SINGLE", "BLEND"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)")
ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def detect_roast(text: str) -> str | None:
    m = ROAST_PATTERN.search(text)
    if m:
        return m.group(1)
    if "焙煎は浅く" in text:
        return "浅煎り"
    return None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if BEAN_TAG not in (p.get("tags") or []) or p.get("product_type") not in BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            if not (v.get("title") or "").startswith("豆のまま"):
                continue
            m = WEIGHT_PATTERN.search(v["title"])
            if m:
                grams = int(m.group(1)) * (1000 if m.group(2) == "kg" else 1)
                weighted.append((grams, v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        roast = detect_roast(body)

        parsed = parse_product(title)
        if p["product_type"] == "BLEND":
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            # 商品説明の「COUNTRY ネパール」表記で補う(商品名が英語表記で国名辞書に無い場合)
            cm = re.search(r"COUNTRY\s*(\S+)", body)
            if not parsed["origin_country"] and cm:
                # 国名辞書に無い国(ネパール等)も、店の表記をそのまま採用する
                parsed["origin_country"] = detect_country_name(cm.group(1)) or cm.group(1)
                parsed["origin_source"] = "description"
            if not parsed["processing_method"]:
                parsed["processing_method"] = detect_processing_method(body[:60])

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
    with open("data_onsaya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_onsaya.json に出力しました")


if __name__ == "__main__":
    main()
