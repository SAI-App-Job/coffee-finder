# -*- coding: utf-8 -*-
"""
scrape_riverbedcoffeebrewerroastery.py

RIVERBED COFFEE BREWER&ROASTERY(riverbedcoffee-brewer-roastery.com、岐阜県中津川市
手賀野74)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`全18件のうち、バリエーション名に
「<重量>g / 豆のまま」を持つ商品(シングルオリジン9種+ハウスブレンド1種)を対象とする。
除外: リキッドアイスコーヒー、ドリップバッグ、コーヒーキャニスター、HARIO製品(器具)。
重量は100g/150g/200g/250gの規格があり、豆のままバリエーションのうち最小重量の価格を
代表とする。焙煎度は商品名末尾の「(浅煎り)」等から取得し、名称から除去する。
精製方法は説明文の「PROCESS : ...」から補完する。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "RIVERBED COFFEE BREWER&ROASTERY",
    "url": "https://riverbedcoffee-brewer-roastery.com/",
    "platform": "Shopify",
    "address": "岐阜県中津川市手賀野74",
    "prefecture": "岐阜県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://riverbedcoffee-brewer-roastery.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"[(（]\s*(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)\s*[)）]")
EXCLUDE_KEYWORDS = ["リキッド", "ドリップバッグ", "キャニスター", "HARIO", "ハリオ"]
# 説明文の「Blend Origin: Brazil, Colombia & Guatemala」より(ハウスブレンド)
BLEND_COMPONENTS = {
    "ハウスブレンド-nakatsugawa-中津川深煎り": ["ブラジル", "コロンビア", "グアテマラ"],
}
PROCESS_PATTERN = re.compile(r"PROCESS\s*[:：]\s*([A-Za-z ]+)")


def extract_flavor_notes(body: str) -> str | None:
    text = re.sub(r"\s+", " ", body)
    text = re.split(r"REGION\s*[:：]", text)[0]
    text = re.sub(r"^[^\w぀-ヿ一-鿿]+", "", text)
    return text.strip()[:400] or None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "豆のまま" not in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, _ in weighted)
        variant = [v for w, v in weighted if w == weight][0]
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        flavor_notes = extract_flavor_notes(body)

        roast_m = ROAST_PATTERN.search(title)
        roast_level = roast_m.group(1) if roast_m else None
        name = ROAST_PATTERN.sub("", title).strip()

        parsed = parse_product(name)
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"]
        if not processing:
            pm = PROCESS_PATTERN.search(re.sub(r"\s+", " ", body))
            if pm:
                processing = detect_processing_method(pm.group(1).strip())

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [
                {"origin_country": c, "percentage": None}
                for c in BLEND_COMPONENTS.get(p["handle"], [])
            ],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{urllib.parse.quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_riverbedcoffeebrewerroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_riverbedcoffeebrewerroastery.json に出力しました")


if __name__ == "__main__":
    main()
