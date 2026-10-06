# -*- coding: utf-8 -*-
"""
scrape_coffeepockettime.py

coffee pocket TIME(coffeepocket-time.com、北海道小樽市張碓町455)の商品情報を取得する。
Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが
「ブレンド」「シングルオリジン」「デカフェ」の商品を対象とする(14件)。
定期便(おまかせ珈琲便)・ドリップバッグ・ギフトBOXは除外。
バリエーションは「<重量> / <豆|粉>」の組(ebinamasutoshi.ブレンドのみ「カルダモン
追加」の選択肢もある)。「豆」(カルダモン追加なし)のバリエーションに限定し、
最小重量(100g)の価格・在庫を代表とする。
焙煎度は商品ページに記載がないためnull。デカフェは説明文の「生豆原産国/グアテマラ」から
産地を取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "coffee pocket TIME",
    "url": "https://coffeepocket-time.com/",
    "platform": "Shopify",
    "address": "北海道小樽市張碓町455",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://coffeepocket-time.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = ("ブレンド", "シングルオリジン", "デカフェ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ORIGIN_DESC_PATTERN = re.compile(r"(?:生豆原産国|生産地)\s*[/:：]\s*([^\s/]+)")


def is_whole_bean_variant(variant_title: str) -> bool:
    """「豆」のバリエーション(粉・カルダモン追加を除く)かを判定する。"""
    if "カルダモン" in variant_title:
        return False
    last = variant_title.split("/")[-1].strip()
    return last == "豆" or last.endswith("（豆）")


def clean_description(body: str) -> str | None:
    body = re.sub(r"[―ー\-]{4,}", " ", body)
    body = body.split("※豆の状態について")[0]
    body = body.replace("※シングルオリジンの価格は仕入れ値により変動いたします", " ")
    body = re.sub(r"\s+", " ", body).strip()
    return body[:400] or None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") not in BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "定期便" in title or "ドリップバッグ" in title or "ギフト" in title:
            continue
        if p["product_type"] == "デカフェ" and "デカフェ" not in title:
            title = f"デカフェ {title}"  # 「【カフェインレス】」のみの商品名を補う

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if not is_whole_bean_variant(vt):
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = clean_description(body)

        parsed = parse_product(title)
        if p["product_type"] == "ブレンド" or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"]:
                om = ORIGIN_DESC_PATTERN.search(body)
                if om:
                    detected = detect_country_name(om.group(1))
                    if detected:
                        parsed["origin_country"] = detected
                        parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)

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
    with open("data_coffeepockettime.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeepockettime.json に出力しました")


if __name__ == "__main__":
    main()
