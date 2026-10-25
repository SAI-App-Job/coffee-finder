# -*- coding: utf-8 -*-
"""
scrape_kitasandocoffee.py

KITASANDŌ COFFEE(kitasandocoffee.com、本店は渋谷区千駄ケ谷4-12-8 SSUビル1F、焙煎拠点は
KITASANDŌ COFFEE Roastery = 港区三田3-9-1 RandL 1F)の商品情報を取得する。Shopify。
SHOP_INFOの住所は焙煎拠点(Roastery)を採用する。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、product_typeが
「コーヒー豆浅煎り/中煎り/深煎り」および「PREMIUM LINE」の商品(スペシャルティ豆約30銘柄)を対象とする。
除外: 【SWM】等の「卸」タグ商品(業務用500g)、水出しコーヒーバッグ、コーヒーお試しセット、
定期便、オリジナルコーヒーバッグ、グッズ(タンブラー・ラテボウル・ピンバッジ)。
バリエーションは「豆 / 50g・100g・200g」の組で、50gは試飲向けの小分けのため100g(豆のまま)を代表とする。
焙煎度はproduct_type(浅煎り/中煎り/深煎り)から取得。PREMIUM LINEは焙煎度の記載なしのため null。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "KITASANDŌ COFFEE Roastery",
    "url": "https://kitasandocoffee.com/",
    "platform": "Shopify",
    "address": "東京都港区三田3-9-1 RandL 1F",
    "prefecture": "東京都",
    "robots_txt_status": "確認済み(2026-10-20、User-agent: *で/products.jsonは許可)",
    "source_note": "公式トップ https://kitasandocoffee.com/ (2026-10-20確認)の店舗一覧に「KITASANDŌ COFFEE Roastery」(港区三田)。"
                   "本店は渋谷区千駄ケ谷4-12-8 SSUビル1F(北参道)で、登録住所は焙煎拠点のRoastery。"
                   "Shopifyの/products.jsonのうち浅煎り・中煎り・深煎り・PREMIUM LINEの豆を100g(豆のまま)で収録。"
                   "自家焙煎の根拠は第三者記事(Time Out Tokyo「自家焙煎を中心に常時約10種類のコーヒー豆」、住所は同記事で港区三田3-9-11 RandL TAKANAWA GATEWAY 1階と表記ゆれあり、公式は3-9-1 RandL 1F)。"
                   "商品データは2026-10-25取得の/products.jsonで、価格・在庫はその時点の値(月初クーポン告知等、運営は現役)。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://kitasandocoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
TYPE_ROAST = {"コーヒー豆浅煎り": "浅煎り", "コーヒー豆中煎り": "中煎り", "コーヒー豆深煎り": "深煎り", "PREMIUM LINE": None}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        ptype = p.get("product_type")
        if ptype not in TYPE_ROAST or "卸" in (p.get("tags") or []):
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k in title for k in ("セット", "コーヒーバッグ", "定期便")):
            continue

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and "豆" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        # 50gは試飲向けの小分け。100gがあれば100gを代表とする
        pref = [x for x in weighted if x[0] == 100] or weighted
        weight, variant = min(pref, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = re.sub(r"\s+", " ", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        desc = body[:400] or None
        m = re.search(r"PROCESS\s*:\s*(.+?)\s+(?:FERMENT|MICROORG|TASTING)", body)
        processing_raw = m.group(1).strip() if m else None
        m = re.search(r"FARM / WS etc\.\s*:\s*(.+?)\s+ALTITUDE", body)
        farm = m.group(1).strip() if m else None
        m = re.search(r"TASTING NOTES\s*:\s*(.+?)(?:\s+(?:プロセスについて|詳細情報|◆|■)|$)", body)
        tasting = m.group(1).strip() if m else None

        parsed = parse_product(title)
        if "ブレンド" in title or "BLEND" in title.upper():
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
        processing = parsed["processing_method"]
        if not processing and processing_raw:
            processing = normalize_processing_method(processing_raw.split(" with ")[0])

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": TYPE_ROAST[ptype],
            "roast_hint": None,
            "flavor_notes": tasting or desc,
            "farm_note": farm,
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
    with open("data_kitasandocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kitasandocoffee.json に出力しました")


if __name__ == "__main__":
    main()
