# -*- coding: utf-8 -*-
"""
scrape_oritie.py

コーヒーロースト オリティエ(cbd.oritie.jp、埼玉県越谷市宮本町3-172-1、
2017年開業、注文ごとの自家焙煎、24時間豆自販機も運営)の商品情報を取得する。
WordPress+WooCommerceで、Store API(/wp-json/wc/store/v1/products)が
plain requestsで取得できる。

【店舗発見の経緯】
2026-09-04の別セッションで「独自ECシステムの構造調査に時間を要する」として
見送られていたが、全国再調査(埼玉県)で再検証し、実体がWooCommerceで
Store APIが利用できることを確認して実装した。

【チェーン判定について】
店名に「豆工房コーヒーロースト」グループ名を含むが、同グループは
「コーヒーを愛し、販売するグループ店を応援する仕入機構」であり
フランチャイズではなく各店が独立経営と案内されている。本プロジェクトでも
同グループの豆工房コーヒーロースト宇都宮店等を既に独立店舗として実装済み
のため、同様に扱う。

【対象商品について】
実データ確認済み(2026-10時点): 全47商品のうち、500gの大容量版(同銘柄の
重複)・セット商品・コーヒー豆ガチャ・ドリップバッグ・ペーパーフィルター
等を除いた単品豆24銘柄を対象とする。商品ページに「焙煎後に約200gに
なるよう生豆240gで計量」と明記されているため重量は全て200g。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "コーヒーロースト オリティエ",
    "url": "https://oritie.jp/",
    "platform": "WooCommerce(Store API)",
    "address": "埼玉県越谷市宮本町3-172-1",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

API_URL = "https://cbd.oritie.jp/wp-json/wc/store/v1/products?per_page=100"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_NAME_KEYWORDS = ("500g", "セット", "豆ガチャ", "ドリップバッグ", "ペーパーフィルター", "フィルター")


def clean_name(name: str) -> str:
    name = re.sub(r"<br\s*/?>", " ", name)
    name = re.sub(r"<[^>]+>", "", name)
    name = name.replace("数量限定", "")
    return re.sub(r"\s+", " ", name).strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def scrape_all_products() -> list[dict]:
    resp = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=30)
    products = resp.json()

    records = []
    for p in products:
        name = clean_name(p["name"])
        if any(kw in name for kw in EXCLUDE_NAME_KEYWORDS):
            continue
        categories = [c["name"] for c in p.get("categories", [])]
        if any(c in ("コーヒーアイテム", "ドリップパック", "セット販売", "おとくな大容量") for c in categories):
            continue

        desc = strip_html(p.get("short_description") or p.get("description") or "")[:500] or None
        price = int(p["prices"]["price"])
        in_stock = bool(p.get("is_in_stock", True))

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name.replace("ガテマラ", "グアテマラ"))
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": "注文時に焙煎度合いを選択可",
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 200,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": p["permalink"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_oritie.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oritie.json に出力しました")


if __name__ == "__main__":
    main()
