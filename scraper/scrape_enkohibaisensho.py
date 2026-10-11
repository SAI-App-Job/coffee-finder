# -*- coding: utf-8 -*-
"""
scrape_enkohibaisensho.py

en. 珈琲焙煎所(en-coffee.jp、岡山県岡山市北区表町1丁目10-28 の岡山表町店。ほかに高知店で計2店)
の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(岡山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、ドリップバッグ・お試しセット・
ギフトラッピングを除く豆商品を対象とする。バリエーションは「<重量> / <焙煎度> / <挽き方>」の組
(ブレンドは「<重量> / <挽き方>」)で、「豆のまま」かつ最小重量のバリエーションを代表とする。
焙煎度は、ストレートのバリエーション名にある「おすすめの焙煎度(ハイ)」等の表記を採用する
(ブレンドは焙煎度の表記がないためnull)。アイスコーヒーブレンドは「豆のまま(200g)」を代表とし、
水出し用パックは除外する。全バリエーションが在庫切れの商品は「完売」とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "en. 珈琲焙煎所",
    "url": "https://en-coffee.jp/",
    "platform": "Shopify",
    "address": "岡山県岡山市北区表町1丁目10-28",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(Shopify標準のrobots.txt。商品・コレクションのHTMLはクロール可と明記)",
}

BASE_URL = "https://en-coffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_HANDLE_KEYWORDS = ("dripbag", "ドリップバッグ", "trial-set", "gift-wrapping")
HEAD_WEIGHT = re.compile(r"^(\d+)")
PAREN_WEIGHT = re.compile(r"（(\d+)g）")
ROAST_PATTERN = re.compile(r"おすすめ(?:の)?焙煎度（([^）]+)）")


def normalize_roast(raw: str) -> str:
    return raw if raw.endswith("ロースト") else raw + "ロースト"


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if any(k in p["handle"] for k in EXCLUDE_HANDLE_KEYWORDS):
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "豆のまま" not in vt:
                continue
            m = HEAD_WEIGHT.search(vt) or PAREN_WEIGHT.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        rm = ROAST_PATTERN.search(variant["title"])
        roast = normalize_roast(rm.group(1)) if rm else None

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        is_blend = "ブレンド" in title or title.startswith("en.")
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
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
            "roast_level": roast or parsed["roast_level"],
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
    with open("data_enkohibaisensho.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_enkohibaisensho.json に出力しました")


if __name__ == "__main__":
    main()
