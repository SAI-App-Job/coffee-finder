# -*- coding: utf-8 -*-
"""
scrape_3cedarscoffee.py

3 CEDARS COFFEE(大分県大分市生石2丁目3-9 の豆店。特定商取引法表記の所在地。
焙煎所 3 CEDARS COFFEE ROASTERY は大分市常行258-3、別府市にカフェ LA ARADA)の
商品情報を取得する。Shopify。

【対象商品】Shopifyの`/products.json`のうちproduct_typeが「Coffee Beans」の商品。
ただし product_type「Coffee Beans」にはドリップバッグ・LOS CAMINOSチケット・
ドリップバッグ100個セットも混在するため、次を除外する。
  - タイトルに「ドリップバッグ」「Dripbags」「チケット」「セット」を含む商品
  - 器具(Coffee Tools)・グッズ(Original Goods)は product_type で除外済み
代表バリエーションは最小重量(全豆種で200g。400g(2bags)・1kg(5bags)は除外)。
豆のまま/中挽きは同価格のため「豆のまま」を代表にする。

【在庫】Shopifyの available に従う。ディカフェは「11/6 発送分予約受付中」
(予約販売)だが available=True のため販売中として扱う。タイトル末尾の
予約注記「( 11/6 発送分予約受付中 )」は raw_name から取り除く(説明文には
予約販売である旨が残る)。

【更新日について】全商品の updated_at がテーマ更新で一律になっているため、
商品更新の根拠にはしない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "3 CEDARS COFFEE",
    "url": "https://3cedarscoffee.com/",
    "platform": "Shopify",
    "address": "大分県大分市生石2丁目3-9",
    "prefecture": "大分県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://3cedarscoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "Coffee Beans"
EXCLUDE_TITLE_KEYWORDS = ["ドリップバッグ", "dripbag", "チケット", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
BLEND_ORIGIN_PATTERN = re.compile(r"生産国\s*[:：]\s*([^\s焙]+(?:、[^\s焙]+)*)")
ROAST_PATTERN = re.compile(r"焙煎度合?\s*[:：]\s*((?:極|中)?(?:浅|深)?煎り|OMNI Roast)")


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.replace("　", " ")).strip()
    t = re.sub(r"\s*\(\s*\d+/\d+\s*発送分予約受付中\s*\)", "", t)
    t = re.sub(r"\s*\d+g\s*$", "", t).strip()
    return t


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        if any(kw.lower() in p["title"].lower() for kw in EXCLUDE_TITLE_KEYWORDS):
            continue

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, v in weighted)
        # 同重量内では「豆のまま」を優先(価格は同一)
        cands = [v for w, v in weighted if w == weight]
        variant = next((v for v in cands if "豆のまま" in v["title"]), cands[0])
        available = bool(variant.get("available"))

        title = clean_title(p["title"])
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None

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

        roast = None
        m = ROAST_PATTERN.search(body)
        if m:
            roast = "オムニロースト" if m.group(1).startswith("OMNI") else m.group(1)

        blend_components = []
        if parsed["category"] == "ブレンド":
            mb = BLEND_ORIGIN_PATTERN.search(body)
            if mb:
                blend_components = [{"origin_country": c} for c in mb.group(1).split("、")]

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
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
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
    with open("data_3cedarscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_3cedarscoffee.json に出力しました")


if __name__ == "__main__":
    main()
