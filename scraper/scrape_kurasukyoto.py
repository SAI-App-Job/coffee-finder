# -*- coding: utf-8 -*-
"""
scrape_kurasukyoto.py

Kurasu Kyoto(jp.kurasu.kyoto、京都府京都市下京区東油小路町552ほか3拠点
[Kurasu Ebisugawa・2050 COFFEE]、自家焙煎豆のオンライン販売)の商品情報を
取得する。Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。Kurasu Kyoto Stand・2050 COFFEE(Kurasu系列)・Kurasu
Ebisugawaの3拠点は同一オンラインストアを共有しているため1店舗として
収録する(代表拠点はKurasu Kyoto Stand)。

【対象カテゴリについて】
実データ確認済み(/products.json全230件、2026-09時点): product_typeが
「シングルオリジン」「ブレンド」「コーヒー豆」の商品を対象とする(器具・
茶・アパレル等は対象外)。「Cold Brew」を含む商品(タイトルにCold Brew、
5bags/10bags単位のパック)は粉末パックでありコーヒー豆単品とは形態が
異なるためNON_BEAN_KEYWORDSで除外。対象16件中Cold Brew3件を除いた13件
を収録。

【重量・価格について】
実データ確認済み: 1商品に複数の重量バリアント(50g/100g/250g/500g/1kg×
豆のまま/挽き豆)が存在する。variants[].gramsは梱包重量を含み実際の
コーヒー量と一致しないため使用せず、バリアント名の重量表記から取得する。
「豆のまま」かつ最小重量のバリアントを代表価格として採用する。

【商品説明について】
実データ確認済み: body_htmlの<h5>または先頭<p>内にテイスティング文が
あるが、Notion由来のHTMLコメント(<!-- notionvc: ... -->)が混入している
ため、bs4.Comment要素を明示的に除外して取得する。焙煎日・発送予定日の
案内文(2つ目以降の<p>)はflavor_notesの対象外とする(最初のブロックのみ
採用)。
"""

import re

import requests
from bs4 import BeautifulSoup, Comment

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "Kurasu Kyoto",
    "url": "https://kurasu.kyoto/",
    "platform": "Shopify",
    "address": "京都府京都市下京区東油小路町552",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://jp.kurasu.kyoto"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_TYPES = {"シングルオリジン", "ブレンド", "コーヒー豆", "Coffee Beans"}
NON_BEAN_KEYWORDS = ["Cold Brew"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]|(\d+)\s*kg", re.IGNORECASE)


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_weight_g(variant_title: str) -> int | None:
    m = re.search(r"(\d+)\s*kg", variant_title, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", variant_title)
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    whole_bean = [v for v in variants if "豆のまま" in (v.get("title") or "")]
    pool = whole_bean or variants
    pool = [v for v in pool if parse_weight_g(v.get("title") or "") is not None]
    if not pool:
        return None
    return min(pool, key=lambda v: parse_weight_g(v["title"]))


def extract_flavor_notes(body_html: str) -> str | None:
    soup = BeautifulSoup(body_html or "", "html.parser")
    first_block = soup.find(["h5", "p"])
    if not first_block:
        return None
    for comment in first_block.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    text = first_block.get_text(" ", strip=True)
    # 発送予定日等の案内文(最初のブロックが該当してしまった場合)は採用しない
    if re.search(r"焙煎日|発送", text):
        return None
    return text or None


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None
    variant = pick_canonical_variant(product.get("variants") or [])
    if not variant:
        return None

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])),
            "product_url": f"{BASE_URL}/products/{product['handle']}",
        }

    parsed = apply_category_hint_fallback(parsed, title)
    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": extract_flavor_notes(product.get("body_html")),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": parse_weight_g(variant["title"]),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = [p for p in fetch_products() if p.get("product_type") in TARGET_TYPES]

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kurasukyoto.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kurasukyoto.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
