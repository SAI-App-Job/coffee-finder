# -*- coding: utf-8 -*-
"""
scrape_imadegawa.py

今出川珈琲(imadegawa coffee、imadegawa.theshop.jp、福島県須賀川市八幡町
22-8、須賀川市役所北側、築50年以上の家屋をリノベーションした自家焙煎
コーヒースタンド)の商品情報を取得する。BASE(theshop.jpドメイン)。

【店舗発見の経緯】
全国再調査(福島県)でarukunet.jp記事から発見。2026年1月開業。

【対象商品について】
実データ確認済み(2026-09時点): 商品一覧全8件のうち、ドリップパック2種
(箱無し/箱入り、いずれも今出川ブレンドの粉タイプ)を除いた、コーヒー豆
6銘柄(150g、ブレンド1・ストレート5)を対象とする。

【商品説明・在庫について】
実データ確認済み: iskoffee.com・Day & Coffee等と同じBASE系列プラット
フォームのため、og:descriptionに自由記述の商品説明があり、GA計測用
インラインJSのitem_purchasability("purchasable"/"unpurchasable")
フィールドで在庫状態を判定する。産地・精選方法等の構造化ラベルは
商品説明に無く、商品名(「コロンビア　[中煎り]」等)から産地・焙煎度の
手がかりを得る。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "今出川珈琲",
    "url": "https://imadegawa.theshop.jp/",
    "platform": "BASE(theshop.jp)",
    "address": "福島県須賀川市八幡町22-8",
    "prefecture": "福島県",
    "tel": "0248-94-7467",
    "robots_txt_status": "未確認(BASE標準構成、iskoffee.com等と同系列プラットフォーム)",
}

BASE_URL = "https://imadegawa.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "71200640",   # 今出川ブレンド [中深煎り] 150g
    "71200661",   # エチオピア [中煎り] 150g
    "119153446",  # コロンビア [中煎り] 150g
    "119162702",  # ペルー [中煎り] 150g
    "71200682",   # タンザニア [深煎り] 150g
    "71200702",   # インドネシア マンデリン [深煎り] 150g
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*imadegawa")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"[［\[]([^］\]]*煎り)[］\]]")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1).strip() if desc_m else None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else 150
    roast_m = ROAST_PATTERN.search(title)
    roast_hint = roast_m.group(1) if roast_m else None

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{item_id}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_imadegawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_imadegawa.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
