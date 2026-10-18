# -*- coding: utf-8 -*-
"""
scrape_nakashimakyujocoffee.py

中島九条珈琲(運営: 長江株式会社。大分本店 大分県大分市中島東3-4-1、
湯布院焙煎所 大分県由布市湯布院町川上3645-1)の商品情報を取得する。Shopify。

【住所について】公式about(店舗アクセス)の大分本店は「中島東3丁目4-1」、
特定商取引法表記(長江株式会社の所在地)は「中島東3-4-3」。店舗として
about記載の 3-4-1 を採用する。

【自家焙煎の根拠】公式の商品タグが「自家焙煎コーヒー豆」、商品内容欄が
「自家焙煎珈琲 ケニアAA 200g」等、aboutが「湯布院焙煎所を1店舗営業」と記載。
ただし焙煎機・焙煎場所を明記した本文は確認できていない。

【対象商品】product_typeが「コーヒー豆」の商品のうち、タイトルに
「ドリップバッグ」を含む商品を除外した4銘柄(中島ブレンド、ケニアAA、
ブルーマウンテンNo.1、グアテマラ アンティグア)。重量はタイトル記載の
値(200g/150g)を採用(Shopify側のgramsは梱包込みで信頼しない)。
豆のまま/中挽きは同価格のため「豆のまま」を代表にする。

【更新日について】全商品の updated_at がテーマ更新で一律になっているため、
商品更新の根拠にはしない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "中島九条珈琲",
    "url": "https://nakashima-kyujo.com/",
    "platform": "Shopify",
    "address": "大分県大分市中島東3-4-1",
    "prefecture": "大分県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://nakashima-kyujo.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
EXCLUDE_TITLE_KEYWORDS = ["ドリップバッグ", "ドリップパック"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
BLEND_PATTERN = re.compile(r"商品名：[^()（）\n]*ブレンド[(（]([^)）]+)[)）]")


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.replace("　", " ")).strip()
    t = re.sub(r"\s*[(（]\s*\d+\s*g\s*[)）]\s*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r'\s*"?\d+\s*g"?\s*$', "", t, flags=re.IGNORECASE)
    return t.strip()


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

        m = WEIGHT_PATTERN.search(p["title"])
        weight = int(m.group(1)) if m else None
        variants = p["variants"]
        variant = next((v for v in variants if "豆のまま" in (v.get("title") or "")), variants[0])
        available = bool(variant.get("available"))

        title = clean_title(p["title"])
        body_text = BeautifulSoup(
            (p.get("body_html") or "").replace("<br>", "\n").replace("</p>", "\n"), "html.parser"
        ).get_text("\n", strip=True)
        body = re.sub(r"\s+", " ", body_text)
        # 先頭の販促文(巾着プレゼント)を除いた説明を保持
        desc = re.sub(r"^\\?[\\/]珈琲豆2袋以上ご購入のお客様にオリジナル巾着プレゼント中\\?/\s*", "", body)[:400] or None

        parsed = parse_product(title)
        blend_components = []
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            mb = BLEND_PATTERN.search(body_text)
            if mb:
                blend_components = [{"origin_country": c.strip()} for c in re.split(r"[、,]", mb.group(1)) if c.strip()]
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        if not parsed["processing_method"]:
            mp = re.search(r"精製方法\s*[:：]\s*(\S+)", body)
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
    with open("data_nakashimakyujocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nakashimakyujocoffee.json に出力しました")


if __name__ == "__main__":
    main()
