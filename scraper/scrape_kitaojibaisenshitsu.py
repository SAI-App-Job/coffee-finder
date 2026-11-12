# -*- coding: utf-8 -*-
"""
scrape_kitaojibaisenshitsu.py

北大路焙煎室(https://kitaoji-roastery-lab.com/、京都府京都市北区小山北上総町40-2 アイ・ビルディング1階)の
商品情報を取得する。Shopify(/products.json)。

【対象商品について】
実データ確認済み(2026-10-21): `/products.json`のうちproduct_typeが「コーヒー」の商品から、
銘柄別のシングルオリジン豆(デカフェ含む)を対象とする。バリエーションは「<重量>g / <挽き方>」で、
最小重量(100g)・「豆のまま」の価格を代表とする。
除外: 5COFFEE SELECTIONS・4周年アソート・焙煎度違い飲み比べ(セット)、COLD BREW(コールドブリューパック)、
コーヒーカップ・器(product_typeがコーヒーカップ・ティーカップ)、
果実・花を加えるインフューズド/共発酵: Honey Sangria Red Wine(青りんご・オレンジ・ブドウを加えて発酵)、
Pina Colada Mossto Co-Fermented(ココナッツ・パイナップルを発酵に使用。3商品)、
India Pearl Mountain Catuai Jasmine(ジャスミン・ラベンダーのドライフラワーと共乾燥)。
"""

import json
import os
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "北大路焙煎室",
    "url": "https://kitaoji-roastery-lab.com/",
    "platform": "Shopify",
    "address": "京都府京都市北区小山北上総町40-2 アイ・ビルディング1階",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10-21確認。Shopify標準のrobots.txtで/products.jsonは禁止されていない)",
    "source_note": "公式Shopify https://kitaoji-roastery-lab.com/products.json を2026-10-21に確認。住所は /policies/legal-notice の所在地(食べログと一致)。自家焙煎の根拠は /pages/shop(自家焙煎のコーヒー豆を販売、イートイン・テイクアウト)と /pages/features(焙煎機LORING S7 Nighthawk)。商品最終更新2026-10-21。インフューズド/共発酵・セット・コールドブリューは除外",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://kitaoji-roastery-lab.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
BEAN_TYPE = "コーヒー"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")

EXCLUDE_HANDLES = {
    "５coffee-selections",
    "4th-anniversary-special-coffee-assortment",
    "guatemala-huehuetenango-quetzal-set",
    "colombia-campo-hermoso-pina-colada-mossto-co-fermented-set",
    "cold-brew-refresh-blend",
    "cold-brew-ethiopia-decaf",
    "colombia-santuario-honey-sangria-red-wine",
    "colombia-campo-hermoso-pina-colada-mossto-co-fermented-deep-roast",
    "colombia-campo-hermoso-pina-colada-mossto-co-fermented",
    "india-pearl-mountain-catuai-jasmine",
}

# 商品説明・商品名で焙煎度が明記されているもの(ハンドル→焙煎度)
ROAST_OVERRIDES = {
    "colombia-santuario-sudan-rume": "浅煎り",            # 4周年アソート説明「3種の浅煎りシングル」
    "kenya-kangocho-washed-deep-roast": "中深煎り",        # 説明「中深煎りに焙煎し」
    "2024-new-crop-guatemala-huehuetenango-quetzal": "中煎り",  # 説明「中煎りですっきり」
    "brazil-tropical-bahia-sweet-natural-deep-roast": "深煎り",  # 商品名 -Deep Roast-
    "cameroon-mbessa-g1-peaberry-washed-deep-roast": "深煎り",
    "guatemala-huehuetenango-quetzal-dark-roast": "深煎り",
}

# 国名辞書(coffee_parser)で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {"cameroon-mbessa-g1-peaberry-washed-deep-roast": "カメルーン"}


def scrape_all_products() -> list[dict]:
    # 環境変数 PRODUCTS_JSON_FILE が指定されていれば、事前に取得済みの /products.json を読む
    # (サイト側が429を返し続ける場合に、過去に取得したスナップショットから生成するため)
    snapshot = os.environ.get("PRODUCTS_JSON_FILE")
    if snapshot:
        with open(snapshot, encoding="utf-8") as f:
            products = json.load(f).get("products", [])
    else:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE or p["handle"] in EXCLUDE_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and "豆のまま" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            print(f"[skip] 豆のまま・重量のバリエーションなし: {p['handle']}")
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)
        desc = desc.replace("保存方法：高温多湿を避け冷暗所で保存してください", "").strip()[:400] or None

        parsed = parse_product(title)
        if parsed["category"] != "ブレンド":
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": ROAST_OVERRIDES.get(p["handle"]) or parsed["roast_level"],
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
    with open("data_kitaojibaisenshitsu.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kitaojibaisenshitsu.json に出力しました")


if __name__ == "__main__":
    main()
