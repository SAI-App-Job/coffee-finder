# -*- coding: utf-8 -*-
"""
scrape_miltoncoffee.py

ミルトンコーヒーロースタリー(Milton Coffee Roastery、山口県周南市)の商品情報を取得する。Shopify。

【店舗情報】
本店(児玉町本店): 山口県周南市児玉町3-7-1(2025-04移転。特定商取引法に基づく表記の連絡先と
「ミルトンについて」ページの本店表記が一致。焙煎所も周南市内)。久米店: 山口県周南市久米中央1-17-7
(店舗数2)。住所は特商法記載の本店を採用。

【対象商品について】
実データ確認済み(2026-10-15): Shopifyの`/products.json`のうち product_type が「コーヒー豆」の
商品から、セット(owners-recommend-5-coffee-set)・ギフト(coffee_beans_giftbox_200g)・
お試しセット(trial-coffee)を除外する。ドリップパック(product_type=ドリップパック)、
コーヒーギフト、カスカラティー等は product_type が別のため対象外。
- 通常商品は200g(商品ページの「挽き目(200g/1袋)」表記、季節ブレンド等は説明に「内容量:200g」)。
  バリエーションは挽き方違いで価格は同一。
- ゲイシャ2種は 100g 商品(`*-100g`)と200g 商品が別商品として並ぶため、最小重量の100gを代表にし、
  200g 商品は除外する。
- 「一時休止」タグの商品は全バリエーションが在庫なし(完売)。完売として収録する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "ミルトンコーヒーロースタリー",
    "url": "https://miltoncoffee.com/",
    "platform": "Shopify",
    "address": "山口県周南市児玉町3-7-1",
    "prefecture": "山口県",
    "robots_txt_status": "未確認(Shopify標準構成。公開の/products.jsonを使用)",
    "source_note": "公式サイト(https://miltoncoffee.com/)のShopify商品データ(/products.json)と特定商取引法に基づく表記を2026-10-15に確認",
    "last_verified_at": "2026-10-15",
}

BASE_URL = "https://miltoncoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"

# セット・ギフト・お試し(product_type が「コーヒー豆」のまま混在)
EXCLUDE_HANDLES = {
    "owners-recommend-5-coffee-set",
    "coffee_beans_giftbox_200g",
    "trial-coffee",
}
# ゲイシャの200g商品(100g商品が別にあるため最小重量の100g側を代表にする)
DUPLICATE_LARGER_HANDLES = {
    "elcorozo-geisha-washed",
    "nicaragua-elite-geisha-natural",
}

COUNTRY_TAGS = {
    "ニカラグア", "エルサルバドル", "コロンビア", "グアテマラ", "ブラジル", "エチオピア",
    "ケニア", "パナマ", "コスタリカ", "ホンジュラス", "ペルー", "インドネシア",
}
ROAST_TAGS = ["中浅煎り", "浅煎り", "中深煎り", "深煎り", "中煎り"]
PROCESS_TAGS = {
    "ウォッシュド処理": "ウォッシュド",
    "ナチュラル処理": "ナチュラル",
    "ハニー処理": "ハニー",
}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
DEFAULT_WEIGHT_G = 200  # 商品ページの「挽き目(200g/1袋)」表記


def clean_text(html: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True))


def extract_flavor(text: str) -> str | None:
    for pat in (r"味わいの特徴\s*(.+?)\s*生産情報", r"風味特徴】\s*(.+?)\s*焙煎度"):
        m = re.search(pat, text)
        if m:
            return m.group(1)[:400]
    text = re.sub(r"^今季分は完売しました。.*?お知らせします。\s*", "", text)
    return text[:400] or None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        if p["handle"] in EXCLUDE_HANDLES or p["handle"] in DUPLICATE_LARGER_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        tags = p.get("tags") or []
        body = clean_text(p.get("body_html"))

        # 重量: タイトル → 説明の内容量 → 既定(200g)
        m = WEIGHT_PATTERN.search(title)
        if m:
            weight = int(m.group(1))
        else:
            m = re.search(r"内容量[:：]\s*(\d+)\s*g", body)
            weight = int(m.group(1)) if m else DEFAULT_WEIGHT_G

        variants = p["variants"]
        price = int(float(variants[0]["price"]))
        available = any(v.get("available") for v in variants)

        parsed = parse_product(title)
        is_blend = "ブレンド" in tags or "ブレンド" in title
        if is_blend:
            parsed["category"] = "ブレンド"
            origin, origin_source = None, None
        else:
            parsed["category"] = "ストレート"
            origin, origin_source = parsed["origin_country"], parsed["origin_source"]
            if not origin:
                for t in tags:
                    if t in COUNTRY_TAGS:
                        origin, origin_source = t, "shop_tag"
                        break
        process = parsed["processing_method"]
        if not process:
            for t, v in PROCESS_TAGS.items():
                if t in tags:
                    process = v
                    break
        roast_hint = next((t for t in ROAST_TAGS if t in tags), None)
        farm = next((t for t in tags if t.endswith("農園")), None)
        variety = next((t for t in tags if t.endswith("種") and not t.startswith("焙煎")), None)
        farm_note = " / ".join(x for x in (farm, variety) if x) or None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": origin,
            "origin_source": origin_source,
            "designated_brand": parsed["designated_brand"],
            "processing_method": process,
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": extract_flavor(body),
            "farm_note": farm_note,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_miltoncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_miltoncoffee.json に出力しました")


if __name__ == "__main__":
    main()
