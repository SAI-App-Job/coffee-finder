# -*- coding: utf-8 -*-
"""
scrape_sawaicoffeehonten.py

澤井コーヒー本店(https://sawaicoffeehonten.com/、愛知県名古屋市東区泉二丁目11番8号)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。1階が焙煎所・コーヒー豆販売、2階がイートインの
実店舗。トップに「1948年創業 自家焙煎珈琲屋」「昭和30年代からのレトロな焙煎機」と明記。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「コーヒー」の
商品(単品種・ブレンド・デカフェ)を対象とする。定期便(beans_subscription)と
デカフェお試しセット(decaf_trial)は除外。各商品の選択肢は「豆のまま / 粉に挽く」×
「50g / 200g / 500g」で、豆のままの最小重量(50g)の価格を代表とする。
商品名に「｜」で続く宣伝文句は取り除き、焙煎度は商品名・説明文の「焙煎度」表記から
下のROASTSに明示している(記載のない商品はNone)。

【robots.txtについて】
User-agent: * は /cart /checkout /account 等のみ制限(2026-10確認)。/products.json は禁止されていない。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "澤井コーヒー本店",
    "url": "https://sawaicoffeehonten.com/",
    "platform": "Shopify",
    "address": "愛知県名古屋市東区泉二丁目11番8号",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10確認。/cart・/checkout・/account等以外は制限なし)",
    "source_note": "Shopify /products.json(product_type=コーヒー)と各商品の説明文を2026-10-21に取得。住所・自家焙煎は https://sawaicoffeehonten.com/pages/shop と トップページ(「1948年創業 自家焙煎珈琲屋」「昭和30年代からのレトロな焙煎機」)で確認。products.jsonのupdated_atは2026-10-21",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://sawaicoffeehonten.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
BEAN_TYPE = "コーヒー"
EXCLUDE_HANDLES = {"beans_subscription", "decaf_trial"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")

# handle -> 焙煎度(商品名・説明文の表記に基づく。記載なしはNone)
ROASTS = {
    "decaf-mexico": "中煎り",
    "decaf-columbia": "深煎り",
    "french-german": "超深煎りと深煎り",
    "nabeyamachi-blend": "中煎りと深煎り",
    "mocha-medium": "中煎り",
    "brazil-medium": "中煎り",
    "columbia-medium": "中煎り",
    "mocha-dark": "深煎り",
    "brazil-dark": "深煎り",
    "columbia-dark": "深煎り",
    "sumatra-mandheling": "中深煎り",
    "bluemountain-no1": "浅煎り",
    "house-blend": "中煎りと深煎り",
    "mild-blend": "中煎り",
    "special-blend": "中煎り",
    "kilimanjaro-blend": "中煎り",
    "mocha-blend": "中煎り",
    "bluemountain-blend": "浅煎りと中煎り",
    "german-roast": "深煎り",
    "french-roast": "超深煎り",
}


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return title.split("｜")[0].strip()


def clean_desc(html: str) -> str | None:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"[―ー]{4,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400] or None


def scrape_all_products() -> list[dict]:
    resp = None
    for attempt in range(6):
        resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code != 429:
            break
        # 429は回避せず、Retry-After(秒)だけ待って間隔を空けて再試行する
        time.sleep(int(resp.headers.get("Retry-After", "60")) + 30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE or p["handle"] in EXCLUDE_HANDLES:
            continue
        title = clean_title(p["title"])

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "粉" in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        parsed = parse_product(title)
        tags = p.get("tags") or []
        if "ブレンド" in tags or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
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
            "roast_level": ROASTS.get(p["handle"]) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": clean_desc(p.get("body_html")),
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
    with open("data_sawaicoffeehonten.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sawaicoffeehonten.json に出力しました")


if __name__ == "__main__":
    main()
