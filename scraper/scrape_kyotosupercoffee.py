# -*- coding: utf-8 -*-
"""
scrape_kyotosupercoffee.py

京都スーパーコーヒー(Kyoto Super Coffee、京都府京都市北区紫野雲林院町22、独自EC=Astro製の静的サイト
https://kyoto-super-coffee.com/)の商品情報を取得する。

【ページ構造】トップページの「焙煎豆」節に商品カード(`article.product-card`、id=`product-<sku>`)が並び、
同じ内容が JSON-LD(ItemList/Product)に載っている。カートはJSだが、商品カードと JSON-LD は静的HTMLに含まれる。
JSON-LD の price は各商品の基準容量(200g)の税込価格。500g/1kg以上は「目方割引」で100gあたりが安くなる
(カード表示の「¥400〜/100g」は最大割引時の100g単価)ので、代表は最小の200g(JSON-LD price)を採用する。
挽き方(豆のまま〜極細挽き)は注文時に選べ、価格は共通。
【除外】ギフトセット(gift-set、浅煎り・中煎りブレンドの詰合せ)。
商品URLはトップページ + `#product-<sku>`(JSON-LD の url と同じ)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "京都スーパーコーヒー",
    "url": "https://kyoto-super-coffee.com/",
    "platform": "独自EC(Astro製)",
    "address": "京都府京都市北区紫野雲林院町22",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。robots.txtは Allow: / 、/nobimamekura/ のみ禁止)",
    "source_note": "トップページの商品一覧(商品カードとJSON-LD)を2026-10-21に確認。住所は特定商取引法ページ https://kyoto-super-coffee.com/legal/tokushoho 。価格は200g基準(目方割引は500g以上)。商品・告知の日付表記は無し",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://kyoto-super-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_SKUS = ("gift-set",)
# 説明文に産地が明記されている単一銘柄(sku -> 産地)。オーガニックは説明文に産地が無いので None
ORIGIN_BY_SKU = {
    "papua-new-guinea-200": "パプアニューギニア",
    "mocha-200": "イエメン",
    "india-monsoon-200": "インド",
    "peru-200": "ペルー",
    "mexico-200": "メキシコ",
    "mandheling-200": "インドネシア",
    "guatemala-200": "グアテマラ",
    "kilimanjaro-200": "タンザニア",
    "santos-200": "ブラジル",
    "colombia-200": "コロンビア",
}
SINGLE_SKUS = set(ORIGIN_BY_SKU) | {"organic-200"}


def fetch_page():
    resp = requests.get(BASE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_jsonld(soup):
    items = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "")
        except ValueError:
            continue
        for g in d.get("@graph", []):
            if g.get("@type") == "ItemList":
                for it in g.get("itemListElement", []):
                    p = it["item"]
                    items[p["sku"]] = p
    return items


def build_record(sku, p, roast):
    name = p["name"]
    parsed = parse_product(name)
    offer = p["offers"]
    sold = not offer.get("availability", "").endswith("InStock")
    if sku in SINGLE_SKUS:
        parsed = apply_category_hint_fallback(parsed, name)
        category = "ストレート"
        origin = ORIGIN_BY_SKU.get(sku)
        origin_source = "shop_attribute" if origin else None
        brand = "マンデリン" if sku == "mandheling-200" else parsed["designated_brand"]
    else:
        category, origin, origin_source, brand = "ブレンド", None, None, None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": brand,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": p.get("description"),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(offer["price"]),
        "weight_g": 200,
        "stock_status": "完売" if sold else "販売中",
        "out_of_stock": sold,
        "product_url": p["url"],
    }


def scrape_all_products():
    soup = BeautifulSoup(fetch_page(), "html.parser")
    items = parse_jsonld(soup)
    roast_by_sku = {}
    for art in soup.select("article.product-card"):
        sku = (art.get("id") or "").replace("product-", "", 1)
        b = art.select_one(".product-roast-badge")
        if sku and b:
            roast_by_sku[sku] = unicodedata.normalize("NFKC", b.get_text(strip=True)).replace("超深煎り", "極深煎り")
    records = []
    for sku, p in items.items():
        if sku in EXCLUDE_SKUS:
            continue
        records.append(build_record(sku, p, roast_by_sku.get(sku)))
    return records


def main():
    records = scrape_all_products()
    with open("data_kyotosupercoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kyotosupercoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"], r["product_url"])


if __name__ == "__main__":
    main()
