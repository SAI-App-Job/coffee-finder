# -*- coding: utf-8 -*-
"""
scrape_townsfolkcoffee.py

townsfolk coffee(townsfolkcoffee.com、石川県金沢市高岡町22-18、運営は合同会社TOWNSFOLK)の
自家焙煎コーヒー豆の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちタグ`col-coffee`の商品。
他社焙煎の【Prolog Coffee】200g品、テイスティングセット・季節のセット、定期便、
ディップ式/水出しコーヒーバッグ、卸販売、器・雑貨は除外。
バリエーションは「<重量>g / <挽き方>」の組で、最小重量(100g)・豆のままの価格を代表とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "townsfolk coffee",
    "url": "https://townsfolkcoffee.com/",
    "platform": "Shopify",
    "address": "石川県金沢市高岡町22-18",
    "prefecture": "石川県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://townsfolkcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"^(\d+)\s*g\b")
EXCLUDE_WORDS = ["Prolog", "セット", "Set", "Subscription", "定期便", "バッグ", "Bag", "卸", "GIFT"]


def clean_title(title: str) -> str:
    """「Ethiopia Shantawane - Natural [シャンタワネ - ナチュラル]」から英語表記側を商品名にする。"""
    title = re.sub(r"\s+", " ", title).strip()
    m = re.match(r"^(.*?)\s*\[(.*)\]\s*$", title)
    if m:
        title = f"{m.group(1).strip()} {m.group(2).strip()}"
    return title


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if "col-coffee" not in (p.get("tags") or []):
            continue
        if any(w in p["title"] for w in EXCLUDE_WORDS):
            continue
        title = clean_title(p["title"])
        title = re.sub(r"^【DECAF】\s*", "DECAF ", title)

        # 豆のまま(重量のみのタイトルで始まるもの)の最小重量バリエーション
        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.match((v.get("title") or "").strip())
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight = min(w for w, _ in weighted)
        same = [v for w, v in weighted if w == weight]
        variant = next((v for v in same if "Whole" in v["title"]), same[0])
        available = any(v.get("available") for v in same)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"^【Prologとtownsfolkの豆を同時購入で200円引き】\s*", "", body)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        roast_level = parsed["roast_level"]
        if "col-blend" in p["tags"] and "DECAF" not in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
        if "DECAF" in title and "デカフェ" not in parsed["post_processing_tags"]:
            parsed["post_processing_tags"].append("デカフェ")
        if "焙煎度合いは中煎り" in body:
            roast_level = "ミディアムロースト"

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
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_townsfolkcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_townsfolkcoffee.json に出力しました")


if __name__ == "__main__":
    main()
