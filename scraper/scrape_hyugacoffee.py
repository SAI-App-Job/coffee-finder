# -*- coding: utf-8 -*-
"""
scrape_hyugacoffee.py

日向珈琲(HYUGA COFFEE、store.hyuga.coffee、宮崎県日向市鶴町1-7-1)の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(宮崎県)の新規発掘で発見。住所はストアの「特定商取引法に基づく表記」
(/policies/legal-notice)の記載(宮崎県日向市鶴町1-7-1)による。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`は189件(過去に公開した完売品を含む)。
そのうち product_type が「コーヒー」の豆(シングルオリジン・ブレンド)のみを対象とする。
次は除外: セット/福箱/BOX/定期便/業務用/COLD BREW COFFEE BAG(ドリップではなく抽出パック)/
コーヒーツール(器具)/インフューズド(フレーバー添加)。
件数が多い(50件超)ため、販売中の商品と、直近1年以内(2025-10-18以降)に公開した完売品に絞る。
バリエーションは「<重量>g / 豆のまま・粉」の組で、最小重量のバリエーションの価格を代表とする
(豆のまま/粉は同一商品)。
"""

import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "日向珈琲",
    "url": "https://store.hyuga.coffee/",
    "platform": "Shopify",
    "address": "宮崎県日向市鶴町1-7-1",
    "prefecture": "宮崎県",
    "robots_txt_status": "許可(Shopify標準。/products.jsonはDisallowされていない)",
}

BASE_URL = "https://store.hyuga.coffee"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー"
SOLD_OUT_CUTOFF = "2025-10-18"  # これ以降に公開した完売品を収録
EXCLUDE_TITLE = re.compile(r"セット|SET|BOX|福箱|定期便|業務用|COLD BREW|インヒューズド|FOR BUSINESS|ANNIVERSARY", re.I)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g(?!\s*[×x])", re.I)


def pick_weight(variants: list[dict], title: str):
    weighted = []
    for v in variants:
        vt = v.get("title") or ""
        if "×" in vt:
            continue
        m = WEIGHT_PATTERN.search(vt)
        if m:
            weighted.append((int(m.group(1)), v))
    if not weighted:
        m = WEIGHT_PATTERN.search(title)
        if m and variants:
            return int(m.group(1)), variants
        return None, []
    weight = min(w for w, _ in weighted)
    return weight, [v for w, v in weighted if w == weight]


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if EXCLUDE_TITLE.search(title):
            continue
        weight, group = pick_weight(p["variants"], title)
        if not weight or not group:
            continue
        available = any(v.get("available") for v in group)
        if not available and (p.get("published_at") or "")[:10] < SOLD_OUT_CUTOFF:
            continue

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if parsed["is_flavored"]:
            continue
        tags = p.get("tags") or []
        if "ブレンド" in title or "ブレンド" in tags:
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
        m = re.search(r"【(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)】", title)
        if m:
            roast = m.group(1)
        else:
            for t in tags:
                if t in ("浅煎り", "中煎り", "中深煎り", "深煎り", "中浅煎り"):
                    roast = t
            if roast is None and ("煎" in title or "ロースト" in title):
                roast = parsed["roast_level"]

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
            "blend_components": [],
            "price": int(float(group[0]["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hyugacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hyugacoffee.json に出力しました")


if __name__ == "__main__":
    main()
