# -*- coding: utf-8 -*-
"""
scrape_golpiecoffee.py

GOLPIE COFFEE(store.golpiecoffee.jp、愛知県名古屋市昭和区駒方町2-4-2)の
オンラインストアの商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、ハンドルが`coffee_`で
始まる焙煎豆商品(シングルオリジン・ブレンド)のみを対象とする(14商品前後)。
product_typeは「レギュラーコーヒー」だが、ギフト・詰め合わせ・ドリップバッグ・
水出し・器具・ギフトカード等も同じ種別に含まれるため、ハンドルで絞り込む。
タイトルに「終売」とある商品は完売扱いで収録する。
バリエーションは「<重量> / <挽き方>」の組で、最小重量(多くは200g、ゲイシャ等は100g)の
価格を代表とする(「200g(100gの袋を2つ)」等の増量選択肢は最小重量ではない)。
焙煎度はタイトル末尾の〈中煎り〉等の表記から取得し、味わいは説明文の
「[Tasting Profile]」から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "GOLPIE COFFEE",
    "url": "https://store.golpiecoffee.jp/",
    "platform": "Shopify",
    "address": "愛知県名古屋市昭和区駒方町2-4-2",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://store.golpiecoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"^\s*(\d+)\s*g")
ROAST_BRACKET = re.compile(r"〈([^〉]*煎り)〉")
EXCLUDE_WORDS = ("セット", "詰め合わせ", "ギフト", "ドリップバッグ", "定期便", "水出し")


def clean_title(raw: str) -> tuple[str, bool]:
    t = re.sub(r"<br\s*/?>", " ", raw)
    t = t.replace("　", " ")
    discontinued = "終売" in t
    t = t.replace("終売", "")
    t = re.sub(r"★[^★]*★", " ", t)
    t = re.sub(r"★\S*", " ", t)
    t = re.sub(r"【[^】]*ロット】", " ", t)
    t = ROAST_BRACKET.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t, discontinued


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if not p["handle"].startswith("coffee_"):
            continue
        if any(w in p["title"] for w in EXCLUDE_WORDS):
            continue
        name, discontinued = clean_title(p["title"])
        rm = ROAST_BRACKET.search(p["title"])
        roast = rm.group(1) if rm else None

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight) and not discontinued

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        tm = re.search(r"\[Tasting Profile\]\s*\n?([^\n]+)", body)
        flavor = tm.group(1).strip() if tm else None
        if not flavor:
            lines = [ln for ln in body.split("\n") if ln and not ln.startswith(("※", "★", "【", "〈"))]
            flavor = re.sub(r"\s+", " ", " ".join(lines))[:200] or None
        om = re.search(r"［原産国］\s*\n([^\n]+)", body)
        origin_block = body[om.start():om.start() + 200] if om else ""
        origin_text = om.group(1).strip() if om else ""
        if not roast:
            rr = re.search(r"焙煎度合いは\s*「?([^」\n]*煎り)", body)
            roast = rr.group(1) if rr else None

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["origin_country"] and origin_text:
                c = detect_country_name(origin_text)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            if not parsed["processing_method"] and origin_block:
                parsed["processing_method"] = detect_processing_method(origin_block)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": flavor,
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
    with open("data_golpiecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_golpiecoffee.json に出力しました")


if __name__ == "__main__":
    main()
