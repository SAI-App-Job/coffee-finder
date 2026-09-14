# -*- coding: utf-8 -*-
"""
scrape_6kakucoffee.py

6かく珈琲(6kakucoffee.base.shop、青森県八戸市小中野8-13-2、自家焙煎豆の
オンライン販売)の商品情報を取得する。BASE(白ラベルドメイン)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
特定商取引法ページ(https://6kakucoffee.base.shop/law)で実データ確認済み
(2026-09時点): 「青森県八戸市小中野8-13-2」との記載を確認。候補リストの
住所と一致。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【対象商品について】
実データ確認済み(sitemap.xml全8件、うちトップ/aboutを除く6件): コーヒー豆は
「炭火焙煎珈琲豆　深煎り/浅煎り　150g×2袋set」「炭火焙煎珈琲豆　浅煎り
150g×2袋set」「炭火焙煎珈琲豆　深煎り　150g×2袋set」の3件のみ(単一ブレンドの
焙煎度違い3種、重量はいずれも150g×2袋=300g)。残り3件(デカフェラテベース・
ナッツとチョコレート・カカオニブのキャラメリゼ)と配送方法選択用ダミー商品
(クロネコヤマト発送)は非対象のためNON_BEAN_KEYWORDSで除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "6かく珈琲",
    "url": "https://6kakucoffee.base.shop/",
    "platform": "BASE",
    "address": "青森県八戸市小中野8-13-2",
    "prefecture": "青森県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://6kakucoffee.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ラテベース", "ナッツ", "キャラメリゼ", "発送"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*[×xX]\s*(\d+)")
WEIGHT_SINGLE_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def parse_weight(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = WEIGHT_SINGLE_PATTERN.search(title)
    return int(m.group(1)) if m else None


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)
    weight_g = parse_weight(title)

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({"title": title, "price": fields["price"], "url": product_url})

    records = []
    flavored_records = []
    for item in all_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_6kakucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_6kakucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
