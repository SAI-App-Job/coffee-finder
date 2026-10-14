# -*- coding: utf-8 -*-
"""
scrape_satoyamacoffee.py

さとやまコーヒー(satoyamacoffee.com、合同会社秋田里山デザイン、秋田県男鹿市船川港船川字栄町89-3)の
商品情報を取得する。Shopify。エチオピアから直輸入・自家焙煎。

【店舗発見の経緯】
全国再調査(秋田県)の新規発掘で発見。公式サイトのフッターと特定商取引法表記(/pages/tradelaw)の
所在地がいずれも「秋田県男鹿市船川港船川字栄町89-3」(2026-10-13確認)。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうち、コーヒー豆に当たる下記HANDLESのみ。
ドリップバッグ・水出しパック・定期便・ギフトセット・ギフトカードは除外。
バリエーションは「豆|粉 / 100g|200g」の組で、豆の最小重量(100g)の価格を代表とする。
「【限定コーヒー】さとやまブレンド」「【会員限定コーヒー#1】全部盛りな感じ」は重量の
記載が商品ページに無いため、重量はnullとする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

SHOP_INFO = {
    "name": "さとやまコーヒー",
    "url": "https://satoyamacoffee.com/",
    "platform": "Shopify",
    "address": "秋田県男鹿市船川港船川字栄町89-3",
    "prefecture": "秋田県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://satoyamacoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")

# handle -> (分類, 産地, 焙煎度, 精製)。商品名が「〜な感じ」で産地等が名前に出ないため、
# 商品ページの説明文(エチオピア・グジ、嫌気性発酵ナチュラル等)に基づき明示する。
HANDLES = {
    "cassis": ("ストレート", "エチオピア", None, "嫌気性発酵ナチュラル"),
    "grape": ("ストレート", "エチオピア", None, "嫌気性発酵ナチュラル"),
    "mandarine": ("ストレート", "エチオピア", None, "キックスタート・ナチュラル"),
    "satoyama_blend": ("ブレンド", None, "深煎り", None),
    "limitedcoffee01": ("ブレンド", None, None, None),
    "会員限定コーヒー-1-全部盛りな感じ": ("ブレンド", None, None, None),
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    products = {p["handle"]: p for p in resp.json().get("products", [])}

    records = []
    for handle, (category, origin, roast, processing) in HANDLES.items():
        p = products.get(handle)
        if p is None:
            print(f"[warn] 商品が見つかりません: {handle}")
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        bean_variants = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if "粉" in vt:
                continue
            m = WEIGHT_PATTERN.search(vt)
            bean_variants.append((int(m.group(1)) if m else None, v))
        if not bean_variants:
            continue
        with_weight = [(w, v) for w, v in bean_variants if w is not None]
        if with_weight:
            weight, variant = min(with_weight, key=lambda x: x[0])
        else:
            weight, variant = None, bean_variants[0][1]
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": category,
            "origin_country": origin,
            "origin_source": "description" if origin else None,
            "designated_brand": None,
            "processing_method": processing,
            "grade": None,
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": [],
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
    with open("data_satoyamacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_satoyamacoffee.json に出力しました")


if __name__ == "__main__":
    main()
