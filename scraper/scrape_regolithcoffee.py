# -*- coding: utf-8 -*-
"""
scrape_regolithcoffee.py

Regolith Coffee(株式会社Regolith Coffee、大分県大分市。特定商取引法表記の
所在地=焙煎所 田原904-1、別に岩田町2-1-11の岩田店)の商品情報を取得する。Shopify。

【住所について】特定商取引法表記(policies/legal-notice)の所在地が
「大分県大分市田原904-1」。卸販売ページに「私たちが自信持って焙煎する
シングルオリジンコーヒー」とあり、自家焙煎。焙煎所(田原)の住所を採用する。

【対象商品】product_typeが「コーヒー豆」の商品のうち、次を除外する。
  - タイトルに「定期便」を含む商品(定期便用の¥0バリエーション商品。
    同名の通常商品が別にあるため重複になる)
  - 「定期便BOX」「まとめて購入Box」(合計500gの詰め合わせ・サブスク)
  - 全バリエーションが¥0の商品
ギフト(product_type空)・ドリップバッグ・器具・水出しセットはproduct_typeで除外済み。
全て100g。Shopify側のgramsは一部0のため、タイトルの「(100g)」を重量とする。
代表バリエーションは「豆/オススメです!」(挽き方違いは全て同価格)。

【注意】ハンドルと商品タイトルが一致しない商品が多い(例: handle
`sumatra-mandheling` の現在のタイトルは Indonesia Java Frinsa Estate)。
商品名はタイトル(現行)を採用し、URLはハンドルで一意。

【更新日について】全商品の updated_at がテーマ更新で一律になっているため、
商品更新の根拠にはしない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "Regolith Coffee",
    "url": "https://regolith-coffee.com/",
    "platform": "Shopify",
    "address": "大分県大分市田原904-1",
    "prefecture": "大分県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://regolith-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
EXCLUDE_TITLE_KEYWORDS = ["定期便", "まとめて購入", "BOX"]
TITLE_WEIGHT = re.compile(r"[(（]\s*(\d+)\s*g\s*[)）]", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"焙煎度\s*[:：]\s*(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
PROCESS_PATTERN = re.compile(r"精選\s*[:：]\s*(.+?)\s*(?:味わい|発酵時間|生産者名)")
FLAVOR_PATTERN = re.compile(r"味わい\s*[:：]\s*(.+?)\s*(?:生産者名|生産地|タイプ|輸出|$)")
COUNTRY_EN_FALLBACK = {
    "Yemen": "イエメン",
    "Papua New Guinea": "パプアニューギニア",
    "El Salvador": "エルサルバドル",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        if any(kw in p["title"] for kw in EXCLUDE_TITLE_KEYWORDS):
            continue
        variants = [v for v in p["variants"] if float(v["price"]) > 0]
        if not variants:
            continue
        m = TITLE_WEIGHT.search(p["title"])
        weight = int(m.group(1)) if m else None
        variant = next((v for v in variants if (v.get("title") or "").startswith("豆")), variants[0])
        available = bool(variant.get("available"))

        title = re.sub(r"\s+", " ", TITLE_WEIGHT.sub("", p["title"])).strip()
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        fm = FLAVOR_PATTERN.search(body)
        flavor = fm.group(1).strip() if fm else None
        desc = flavor or body[:400] or None

        parsed = parse_product(title)
        if "Blend" in title or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            if not parsed["origin_country"]:
                for kw, c in COUNTRY_EN_FALLBACK.items():
                    if kw.lower() in title.lower():
                        parsed["origin_country"] = c
                        parsed["origin_source"] = "raw_name"
                        break
            if not parsed["origin_country"]:
                detected = detect_country_name(title)
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        if not parsed["processing_method"]:
            mp = PROCESS_PATTERN.search(body)
            if mp:
                parsed["processing_method"] = detect_processing_method(mp.group(1))

        mr = ROAST_PATTERN.search(body)
        roast = mr.group(1) if mr else None

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
    with open("data_regolithcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_regolithcoffee.json に出力しました")


if __name__ == "__main__":
    main()
