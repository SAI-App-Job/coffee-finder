# -*- coding: utf-8 -*-
"""
scrape_kosuitei.py

珈水亭(kosuitei.com、埼玉県熊谷市末広3-12-4の熊谷銀座本店と駅ビルAZ店の
2店舗)のコーヒー豆通販ページの商品情報を取得する。洋食喫茶だが「オーナー自ら
半直火焙煎」と明記されており、自家焙煎豆の通販(代金引換・カード決済)を
行っている。WordPress上の静的ページ。

【店舗発見の経緯】
2026-09-04の別セッションで「独自ECシステムの構造調査に時間を要する」として
見送られていたが、全国再調査(埼玉県)で再検証し、通販ページ
(/category/item/)がplain requestsで全商品の銘柄・価格・説明を取得できる
静的ページであることを確認して実装した。

【対象商品について】
実データ確認済み(2026-10時点): 「ブレンドコーヒー」5銘柄・
「ストレートコーヒー」8銘柄の計13商品。各銘柄は「ロースト豆・200g」
「粉末・200g」「ドリップバッグ(10g)」の3形態があるが、豆の販売価格として
ロースト豆200gの価格のみを収録する(粉末は同価格、ドリップバッグは別形態)。
価格は店頭価格より150円引きの通販価格(一部銘柄)。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈水亭",
    "url": "https://kosuitei.com/",
    "platform": "自社サイト(WordPress、静的な通販ページ)",
    "address": "埼玉県熊谷市末広3-12-4",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://kosuitei.com/category/item/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

FEATURE_PATTERN = re.compile(r"^(.+?)の特徴：(.+)$")
BEAN_LINE_PATTERN = re.compile(r"^(.+?)（ロースト豆・200g入り）$")
PRICE_PATTERN = re.compile(r"^¥([\d,]+)$")


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    lines = [ln.strip() for ln in BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True).split("\n") if ln.strip()]

    start = next(i for i, ln in enumerate(lines) if ln == "通販商品一覧")
    section = None
    descriptions: dict[str, str] = {}
    records = []
    for i in range(start, len(lines)):
        ln = lines[i]
        if ln in ("ブレンドコーヒー", "ストレートコーヒー"):
            section = ln
            continue
        if ln.startswith("珈水亭では、オーナーが"):
            break
        m = FEATURE_PATTERN.match(ln)
        if m:
            descriptions[m.group(1)] = m.group(2)
            continue
        m = BEAN_LINE_PATTERN.match(ln)
        if m and i + 1 < len(lines):
            price_m = PRICE_PATTERN.match(lines[i + 1])
            if not price_m:
                continue
            name = m.group(1)
            parsed = parse_product(name)
            if section == "ブレンドコーヒー":
                parsed["category"] = "ブレンド"
                parsed["origin_country"] = None
                parsed["origin_source"] = None
            else:
                detected = detect_country_name(name)
                if detected and not parsed["origin_country"]:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "raw_name"
                parsed = apply_category_hint_fallback(parsed, name)
                if not parsed["origin_country"]:
                    # 「エメラルドマウンテン」は商品名に国名が無いが説明文に「コロンビアの宝石」と明記
                    detected = detect_country_name(descriptions.get(name, ""))
                    if detected:
                        parsed["origin_country"] = detected
                        parsed["origin_source"] = "product_description"
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
                "roast_hint": None,
                "flavor_notes": descriptions.get(name),
                "farm_note": None,
                "post_processing_tags": parsed["post_processing_tags"],
                "blend_components": [],
                "price": int(price_m.group(1).replace(",", "")),
                "weight_g": 200,
                "stock_status": "販売中",
                "out_of_stock": False,
                "product_url": f"{PAGE_URL}#{quote(name)}",  # 同一ページに複数商品があるため、商品IDを一意にするフラグメントを付ける
            })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kosuitei.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kosuitei.json に出力しました")


if __name__ == "__main__":
    main()
