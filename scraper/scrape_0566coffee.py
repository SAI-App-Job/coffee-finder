# -*- coding: utf-8 -*-
"""
scrape_0566coffee.py

0566珈琲製作所(0566cafe.com、愛知県知立市昭和1丁目12-4)のオンラインショップの
商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうち、次のハンドルの焙煎豆商品のみを対象とする。
  オリジナルブレンド3(0566blend / honeyblend / strongblend)
  シングルオリジン(myanmer / kopi-luwak / geisha / galapagos / 伝説のコーヒー-1-リベリカ)
  美味しいデカフェ(decaf-light / decaf-rich)
  ハイブリッドコーヒー(rum / gin / wine / sake)
除外: 定期便限定品(sub*)、ドリップバッグ・テトラコーヒーバッグ、各種セット・ギフト、
「美味しいデカフェ」お試しセット、「ハイブリッドコーヒー アロマバッグ」(上記ラム・ジン・
ワイン・和酒の各商品のバリエーションと重複するため)、リキュール、ラッピング等。
ハイブリッドコーヒーは「コーヒーとアルコール飲料との融合」を謳う香り付けコーヒー(ノンアルコール)
のため、分類は「フレーバー」とする。

【重量・価格】
バリエーション名中の「<数字>g」(例:「50g / 豆のまま」「アロマバッグ100g / 豆のまま」)の
うち最小重量のバリエーションの価格を代表とする(コルクボトル150gよりアロマバッグ100gが小さい)。
焙煎度は商品説明に明記がないため、記載があれば抽出し、なければnullとする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "0566珈琲製作所",
    "url": "https://0566cafe.com/",
    "platform": "Shopify",
    "address": "愛知県知立市昭和1丁目12-4",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://0566cafe.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")

BLEND_HANDLES = ["0566blend", "honeyblend", "strongblend"]
SINGLE_HANDLES = ["myanmer", "kopi-luwak", "geisha", "galapagos", "伝説のコーヒー-1-リベリカ"]
DECAF_HANDLES = ["decaf-light", "decaf-rich"]
HYBRID_HANDLES = ["hybridcoffee-rum", "hybridcoffee-gin", "hybridcoffee-wine", "hybridcoffee-sake"]
TARGET_HANDLES = BLEND_HANDLES + SINGLE_HANDLES + DECAF_HANDLES + HYBRID_HANDLES


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = {p["handle"]: p for p in resp.json().get("products", [])}

    records = []
    for handle in TARGET_HANDLES:
        p = products.get(handle)
        if not p:
            print(f"[warn] 商品が見つからない: {handle}")
            continue
        title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()

        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "")
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        body = re.split(r"《「のし」", body)[0]
        desc = re.sub(r"\s+", " ", body)[:300] or None
        rm = ROAST_PATTERN.search(body)
        roast = rm.group(1) if rm else None

        parsed = parse_product(title)
        if handle in BLEND_HANDLES:
            parsed["category"] = "ブレンド"
            parsed["processing_method"] = None  # 「ハニーブレンド」の「ハニー」は精選方法ではない
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        elif handle in HYBRID_HANDLES:
            parsed["category"] = "フレーバー"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"] and handle != "伝説のコーヒー-1-リベリカ":
                c = detect_country_name(body.replace("グァテマラ", "グアテマラ"))
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            if not parsed["origin_country"] and "ガラパゴス" in title:
                parsed["origin_country"] = "エクアドル"  # ガラパゴス諸島はエクアドル領
                parsed["origin_source"] = "region_name"
            parsed["category"] = "ストレート"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,  # 商品名の「ライト」「ハイブリッド」等は焙煎度ではないため parse_product の結果は使わない
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{handle}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_0566coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_0566coffee.json に出力しました")


if __name__ == "__main__":
    main()
