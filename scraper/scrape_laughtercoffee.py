# -*- coding: utf-8 -*-
"""
scrape_laughtercoffee.py

Laughter Coffee(laughter-coffee.myshopify.com、京都府京都市伏見区深草塚本町67
紫光館1F)の商品情報を取得する。Shopify。

【対象商品について】
Shopifyの`/products.json`のうち、バリエーションが「<重量>g / 豆のまま・粉」形式の
焙煎豆(ブレンド3種・カフェインレス・シングルオリジン4種)を対象とする。
シングルオリジンも同一ストア内の別商品として並んでおり、別ページ・別サイトは
無い(実データ確認済み)。定期便・ドリップバッグ・ギフトBOX・水出しパック・
生豆(green beans)・雑貨は除外。代表は最小重量(100g)のバリエーションとする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Laughter Coffee",
    "url": "https://laughter-coffee.myshopify.com/",
    "platform": "Shopify",
    "address": "京都府京都市伏見区深草塚本町67 紫光館1F",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://laughter-coffee.myshopify.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
EXCLUDE_KEYWORDS = ("定期便", "ドリップバッグ", "ドリップバック", "ギフト", "セット", "水出し", "green beans", "生豆",
                    "タンブラー", "トート", "ステッカー", "コーヒー缶", "Tシャツ", "マグ")
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り|ライトロースト")),
    ("中煎り", re.compile(r"中煎り|ミディアムロースト")),
    ("深煎り", re.compile(r"深煎り|ダークロースト|フレンチ|イタリアン")),
)
# ブレンド・単品とも名称に焙煎度が出ない商品の補完(商品説明の記述に基づく)
DESC_ROAST = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    seen = set()
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
            continue
        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["origin_country"] and re.search(r"[ 　]タイ$", title):
                parsed["origin_country"] = "タイ"
                parsed["origin_source"] = "raw_name"

        roast_level, roast_hint = coarse_roast(title)
        # ブレンドの説明文には構成豆の名称(チャーリー浅煎り等)が出るだけで、ブレンド自体の
        # 焙煎度を示さないため、焙煎度はシングルのみ説明文から補完する
        if not roast_level and parsed["category"] != "ブレンド":
            m = DESC_ROAST.search(body)
            if m:
                roast_level, roast_hint = coarse_roast(m.group(1))

        url = f"{BASE_URL}/products/{p['handle']}"
        if url in seen:
            continue
        seen.add(url)
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
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_laughtercoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_laughtercoffee.json に出力しました")


if __name__ == "__main__":
    main()
