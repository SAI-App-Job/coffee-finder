# -*- coding: utf-8 -*-
"""
scrape_haizcoffee.py

haiz coffee roastery(haizcoffee.com、富山県南砺市本町3丁目35)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(富山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`の12商品のうち、定期便(subscription)と
インフューズド(Geisha Blend infused)を除くコーヒー豆10銘柄を対象とする。バリエーションは
「豆のまま」と「粉」の組(100g/150g/200g/1kg)で、豆のままの最小重量バリエーションを代表とする。
重量がバリエーション名に無い商品(Granja Paraiso 92)はShopifyのバリエーション重量(grams)を使う。
産地はいずれもコロンビア(商品説明の地域表記。Geisha Washedは説明が途中で切れており農園名Finca Lusitania(同店の他商品でHuila, Colombiaと記載)から判定)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "haiz coffee roastery",
    "url": "https://haizcoffee.com/",
    "platform": "Shopify",
    "address": "富山県南砺市本町3丁目35",
    "prefecture": "富山県",
    "robots_txt_status": "許可(Shopify標準構成、商品JSONは公開)",
}

BASE_URL = "https://haizcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
EXCLUDE_HANDLES = {"subscription", "geisha-blend-infused-ゲイシャブレンド-インフューズド"}


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title.replace("｜", "|")).strip()
    # 「Uba Geisha nitro |  ウバ  ゲイシャニトロ」のような重複併記はそのまま保持
    return title


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p["handle"] in EXCLUDE_HANDLES or "infused" in p["title"].lower():
            continue
        title = clean_title(p["title"])

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "粉" in vt or "Ground" in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weight = int(m.group(1))
            elif v.get("grams"):
                weight = int(round(float(v["grams"])))
            else:
                continue
            weighted.append((weight, v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)
        fm = re.search(r"フレーバーノート\s*(.+?)(?:プロデューサー|加工者|農園|$)", desc)
        flavor = re.sub(r"\s+", " ", fm.group(1)).strip()[:400] if fm else desc[:400]

        parsed = parse_product(title)
        if "ブレンド" in title or "Blend" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["origin_country"] and re.search(r"Colombia|コロンビア|Huila|Hulia|ウイラ|ウィラ|Lusitania", desc):
                parsed["origin_country"] = "コロンビア"
                parsed["origin_source"] = "description"

        roast = parsed["roast_level"]
        if not roast and "Dark" in title:
            roast = "深煎り"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": flavor or None,
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
    with open("data_haizcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_haizcoffee.json に出力しました")


if __name__ == "__main__":
    main()
