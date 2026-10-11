# -*- coding: utf-8 -*-
"""
scrape_coffeegallery.py

珈琲回廊(コーヒーギャラリー。coffeegallery.online、熊本県熊本市中央区西唐人町20)の商品情報を
取得する。Shopify。注文を受けてから焙煎する自家焙煎店(各商品説明に「注文を受けてから焙煎し
新鮮な珈琲豆をお届けしております」と明記)。

【店舗発見の経緯】
全国再調査(熊本県)で発見。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(61件)のうち、商品名に「200g」を含む
コーヒー豆(シングルオリジン・ブレンド・デカフェ)。バリエーションは「豆/細挽き/中挽き/粗挽き/
生豆」で、「豆」の価格・在庫を代表とする。ギフトセット、2種セット、ドリップバッグ、
コールドブリューパック、冷やしコーヒー、ラテベース、キャニスター、器具・雑貨は除外。

【重量・焙煎度の注意】
商品説明に「上記のg表記は生豆の重量です。焙煎度合いは当店推奨焙煎となります」とある。
そのため weight_g は生豆200g換算(焙煎後の内容量ではない)。焙煎度は店の推奨焙煎で
個別に表記が無いため、商品名に明記のあるもの(ブレンド黒=深煎り、ブレンド白=浅煎り)以外は
null。ハンドル(URL)と商品名が食い違う商品が多いので、商品名はtitleを採用し、
product_urlはhandle(商品ごとに一意)を使う。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲回廊",
    "url": "https://coffeegallery.online/",
    "platform": "Shopify",
    "address": "熊本県熊本市中央区西唐人町20",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://coffeegallery.online"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_WORDS = ("キャニスター", "ギフト", "セット", "インスタント", "ドリップ", "コールドブリュー", "ラテ", "冷やし")
ROAST_PATTERN = re.compile(r"[（(](中深煎り|中浅煎り|深煎り|中煎り|浅煎り)[）)]")


def scrape_all_products() -> list[dict]:
    products = []
    for page in range(1, 5):
        r = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        batch = r.json().get("products", [])
        if not batch:
            break
        products += batch

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        ntitle = unicodedata.normalize("NFKC", title)
        if not re.search(r"200\s*g", ntitle, re.I) or any(w in ntitle for w in EXCLUDE_WORDS):
            continue
        variant = next((v for v in p["variants"] if (v.get("title") or "").strip() == "豆"), None)
        if variant is None:
            continue
        available = bool(variant.get("available"))

        body = re.sub(r"\s+", " ", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        desc = body[:400] or None

        parsed = parse_product(title)
        if parsed["category"] == "ブレンド" or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)

        roast_level = parsed["roast_level"]
        m = ROAST_PATTERN.search(ntitle)
        if m:
            roast_level = m.group(1)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": 200,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeegallery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeegallery.json に出力しました")


if __name__ == "__main__":
    main()
