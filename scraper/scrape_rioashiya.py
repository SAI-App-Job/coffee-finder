# -*- coding: utf-8 -*-
"""
scrape_rioashiya.py

RIO COFFEE 芦屋本店(ashiya-rio.jp、兵庫県芦屋市茶屋之町4-12-104、神戸北野などにも
店舗あり)の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のproduct_typeが「Beans」の37件のうち、
自家焙煎の焙煎豆(シングルオリジン A〜D・S・DECAF・限定ロット、定番ブレンド3種+芦屋
プレミアム)のみを対象とする。以下は除外する。
  - セット・詰め合わせ・ギフト(極みセット、飲み比べセット、ABCDセット、ブレンド3種
    セット、飲み比べギフト、全8種セット)
  - 定期便・毎月便・サブスク(「【毎月便】」「毎月○○gお届け便」「Subscription」、
    「④ブレンド単品【各500g】」「③A,B,C,D単品【各500g】」等の送料込み500g商品群は
    いずれも500g専用のまとめ売り枠のため、別途200g商品と重複するので除外)
  - 1kg大容量(RIO blend / RIO NERO Blend / ASHIYA PREMIUM blend 1kg。同名の200g商品が
    あるため代表は200g商品に統一)、お得コーヒー1kg(テストロースト等の混合ロット)、
    バターコーヒー専用豆、【終売】Rwanda Sovu(販売終了)
バリエーションは「<重量> / 豆|粉」の組で、豆(粉でないもの)の最小重量のバリエーションの
価格・在庫を代表とする。

【価格について】
特定商取引法ページ・端数(2,367円=2,152円x1.1、1,944円=1,800円x1.08等)から税込表示で
あることを確認済み。`products.json`のpriceは税込。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "RIO COFFEE 芦屋本店",
    "url": "https://ashiya-rio.jp/",
    "platform": "Shopify",
    "address": "兵庫県芦屋市茶屋之町4-12-104",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://ashiya-rio.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "Beans"
EXCLUDE_KEYWORDS = [
    "セット", "ギフト", "毎月", "お届け便", "Subscription", "定期", "単品【各500g】",
    "単一農園)単品", "1kg", "お得コーヒー", "バターコーヒー", "終売", "福袋",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_HINT_PATTERN = re.compile(r"(Light|Medium Dark|Medium|Dark)\s*Roast", re.I)


def fetch_products() -> list[dict]:
    products, page = [], 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
    return products


def pick_variant(p: dict):
    """豆(粉でない)の最小重量バリエーションを返す。"""
    cands = []
    for v in p["variants"]:
        t = v.get("title") or ""
        if "粉" in t:
            continue
        m = WEIGHT_PATTERN.search(t)
        if m:
            cands.append((int(m.group(1)), v))
    if not cands:
        return None
    return min(cands, key=lambda x: x[0])


def build_record(p: dict) -> dict | None:
    if p.get("product_type") != BEAN_TYPE:
        return None
    title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
    title = re.sub(r"^【NEW[！!]*】\s*", "", title)
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    picked = pick_variant(p)
    if not picked:
        return None
    weight, variant = picked

    body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body)
    desc = body.split("【農園情報】")[0].split("【生産国】")[0].strip()[:400] or None

    parsed = parse_product(title)
    if "blend" in title.lower() or "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(title)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    m = ROAST_HINT_PATTERN.search(title)
    roast_hint = m.group(0) if m else None
    if not roast_hint:
        m2 = re.search(r"(Light|Medium Dark|Medium|Dark)\s*Roast", body[:40], re.I)
        roast_hint = (m2.group(1) + " Roast") if m2 else None
    if not roast_hint:
        for tag in p.get("tags") or []:
            m3 = re.match(r"Type_(Light|Medium Dark|Medium|Dark)", tag)
            if m3:
                roast_hint = m3.group(1) + " Roast"
                break

    available = bool(variant.get("available"))
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
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/products/{p['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_rioashiya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rioashiya.json に出力しました")


if __name__ == "__main__":
    main()
