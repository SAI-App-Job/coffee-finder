# -*- coding: utf-8 -*-
"""
scrape_irocoffee.py

iro coffee(irocoffee2f.thebase.in、青森県弘前市野田1丁目3-16 アンジェリック
弘前店2F、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(青森県)で発見(aomori-and-you.com「青森県内のおすすめコーヒー
ショップ10選」)。

【対象商品について】
実データ確認済み(sitemap.xml全7件、2026-09時点): 全件がストレートコーヒー
豆で、非対象商品(グッズ・ギフト等)は無い。商品名に「100g」の明記が無い
商品もあるが、同店の他商品(明記あり)と価格帯が一致しており、この店舗の
標準販売単位は100gと判断した。

【商品説明の構造について】
実データ確認済み: og:descriptionはテイスティング文のみのシンプルな構成で、
産地・精製方法等の構造化ラベルは無い(産地国・精製方法は商品名からの
検出に委ねる)。

【在庫状態について】
実データ確認済み: 一覧ページには「SOLD OUT」バッジが表示される商品が
あるが、これは商品名(og:title)やog:descriptionには一切反映されない
UI要素のため、通常のdetect_stock_status(商品名テキストのみを見る)では
検出できない。詳細ページ本文に`<p class="item-detail_soldOut_...">
SOLD OUT</p>`という構造化マークアップがあるため、これを正規表現で
検出しstructural_out_of_stockとしてdetect_stock_status()に渡す。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "iro coffee",
    "url": "https://irocoffee2f.thebase.in/",
    "platform": "BASE",
    "address": "青森県弘前市野田1丁目3-16 アンジェリック弘前店2F",
    "prefecture": "青森県",
    "robots_txt_status": "未確認(BASE標準構成を想定)",
}

BASE_URL = "https://irocoffee2f.thebase.in"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
SOLD_OUT_PATTERN = re.compile(r'class="item-detail_soldOut_[^"]*"')


def fetch_item_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=20)
    return sorted(set(re.findall(r"/items/(\d+)", resp.text)))


def build_record(pid: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{pid}", headers=REQUEST_HEADERS, timeout=20)
    html = resp.text
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if not title_m:
        return None
    title = title_m.group(1).split(" | ")[0].strip()

    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', html)
    price = int(float(price_m.group(1))) if price_m else None
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    flavor_notes = desc_m.group(1).strip() if desc_m else None

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{pid}"
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

    detected = detect_country_name(title) or (flavor_notes and detect_country_name(flavor_notes))
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    structural_out_of_stock = bool(SOLD_OUT_PATTERN.search(html))
    stock_status = detect_stock_status(title, structural_out_of_stock=structural_out_of_stock)

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
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in fetch_item_ids():
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_irocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_irocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
