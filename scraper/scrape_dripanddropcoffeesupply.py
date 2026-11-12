# -*- coding: utf-8 -*-
"""
scrape_dripanddropcoffeesupply.py

DRIP & DROP COFFEE SUPPLY(https://drpdrp.com/、京都府京都市上京区笹屋町通智恵光院西入ル笹屋町1-519 Marble BLDG. B1F)
の商品情報を取得する。Shopify(/products.json)。

【対象商品について】
実データ確認済み(2026-10-21): 豆の7商品(Burundi Yandaro、El Salvador Rene Aguilar Pacamara、
AUTUMN BLEND、ICE COFFEE BLEND、ORIGINAL BLEND、STRONG BLEND、LATTE ART BLEND)を対象とする。
バリエーションは重量1種(200g、LATTE ART BLENDのみ500g)x挽き方で、「豆/Beans」の価格を採用する。
除外: ドリップバッグ、BLEND ASSORTMENT(100gx3の詰め合わせ)、各種GIFT、COFFEE STARTER KIT、COLD BREW、
マグ・缶・てぬぐい等のグッズ(商品タイプがCOFFEE/GIFT/GEARと混在するため、下のBEAN_HANDLESで明示)。
店舗は京都市内3店(焙煎所=上京区笹屋町、銀閣寺店、寺町店)ほか城崎店・ひらかたパーク店など、11店舗未満。
"""

import json
import os
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "DRIP & DROP COFFEE SUPPLY",
    "url": "https://drpdrp.com/",
    "platform": "Shopify",
    "address": "京都府京都市上京区笹屋町通智恵光院西入ル笹屋町1-519 Marble BLDG. B1F",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10-21確認。Shopify標準のrobots.txtで/products.jsonは禁止されていない)",
    "source_note": "公式Shopify https://drpdrp.com/products.json を2026-10-21に確認。住所は https://drpdrp.com/pages/kyoto のROASTERY(京都焙煎所)の所在地で /policies/legal-notice(株式会社マーブル、〒602-8453)と一致。「高品質な生豆を小型の焙煎機で少量ずつ丁寧に焼き上げるマイクロロースタリー」。/pages/about にディードリッヒ焙煎機の記載。商品最終更新2026-10-21(AUTUMN BLEND 2026-09-17作成)",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://drpdrp.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")

# 豆の商品のハンドル → (ブレンドか, 焙煎度)。焙煎度は商品説明に明記があるものだけ
BEAN_HANDLES = {
    "indonesia-west-java-sadayana-fw-200g-コピー": (False, None),   # Burundi Yandaro CWS Washed
    "nicaragua-el-naranjo-200g-コピー-1": (False, None),             # El Salvador Rene Aguilar Pacamara Washed
    "summer-blend-200g-コピー": (True, None),                        # AUTUMN BLEND
    "strong-blend-200g-コピー": (True, None),                        # ICE COFFEE BLEND
    "drip-drop-original-blend": (True, None),                        # ORIGINAL BLEND
    "drip-drop-strong-blend": (True, "深煎り"),                      # STRONG BLEND(説明「最も焙煎が深く…深煎りコーヒー」)
    "drip-amp-drop-latte-art-brend": (True, None),                   # LATTE ART BLEND(ハンドル・商品名の表記はBREND)
}
ORIGIN_OVERRIDES = {
    "indonesia-west-java-sadayana-fw-200g-コピー": "ブルンジ",
    "nicaragua-el-naranjo-200g-コピー-1": "エルサルバドル",
}


def load_products() -> list[dict]:
    # 環境変数 PRODUCTS_JSON_FILE が指定されていれば、事前に取得済みの /products.json を読む
    # (サイト側が429を返し続ける場合に、過去に取得したスナップショットから生成するため)
    snapshot = os.environ.get("PRODUCTS_JSON_FILE")
    if snapshot:
        with open(snapshot, encoding="utf-8") as f:
            return json.load(f).get("products", [])
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("products", [])


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return re.sub(r"\s*\d+g$", "", title)


def scrape_all_products() -> list[dict]:
    records = []
    for p in load_products():
        if p["handle"] not in BEAN_HANDLES:
            continue
        is_blend, roast = BEAN_HANDLES[p["handle"]]
        title = clean_title(p["title"])

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and "Beans" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            print(f"[skip] 豆のバリエーションなし: {p['handle']}")
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

        parsed = parse_product(title)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
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
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{quote(p['handle'])}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_dripanddropcoffeesupply.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dripanddropcoffeesupply.json に出力しました")


if __name__ == "__main__":
    main()
