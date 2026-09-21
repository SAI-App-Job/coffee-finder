# -*- coding: utf-8 -*-
"""
scrape_tomiokacoffee.py

富岡珈琲(shop.tomioka-coffee.com、〒719-3115 岡山県真庭市中396-1
真庭あぐりガーデン内、自家焙煎豆のオンライン販売)の商品情報を取得する。
BASE。

【住所について】
公式サイト(https://tomioka-coffee.com/store)の店舗案内ページで実データ
確認したところ、本店の住所は候補リストと一致することを確認した
(2026-09時点。他に津山店・岡山店の支店あり)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品構成について】
実データ確認済み(sitemap.xml全47件): コーヒー豆単品11銘柄(オリヂナル
ブレンドNO.0〜NO.3・イエメン・インドネシア ミトラG1・ルワンダ・
コスタリカ フォレストマウンテン・ブラジル イエローブルボン・グァテマラ
アンティグア・グァテマラカフェインレスコーヒー、いずれも100g/200gの
2重量)と、非対象の送料追加案内(商品ではない)、「【定期便】ドリップ
バッグコーヒー」各種(定期購入)、「ドリップバッグコーヒー...ジャンボリー
パック」各種(ドリップバッグ形態)、「【冷珈琲ドリップバッグ】」各種、
「富岡珈琲のおくりもの」「珈琲ギフト」「定番/選べる珈琲ギフト」
「人気のブレンドとドリップパックの詰め合わせセット」(ギフト・詰め合わせ)、
ワッペン・トートバッグ・Tシャツ・マグカップ(雑貨)。NON_BEAN_KEYWORDSで
除外する。

【重量違いの重複について】
実データ確認済み: 対象11銘柄はいずれも100g/200gの2種類の重量で別々の
商品ページとして登録されている。商品名末尾の重量表記を除いた基準名で
グルーピングし、最小重量(100g)を代表として採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionの先頭に「<商品名> <重量>g/袋。」という
商品名・重量の繰り返しが入り、続けてテイスティング文が地続きで入って
いる(対象11件全て確認)。先頭の重量/袋表記までを除去し、以降をそのまま
採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "富岡珈琲",
    "url": "https://shop.tomioka-coffee.com/",
    "platform": "BASE",
    "address": "岡山県真庭市中396-1 真庭あぐりガーデン内",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.tomioka-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "送料追加", "ジャンボリーパック", "ドリップバッグ", "ドリップパック",
    "ギフト", "セット", "ワッペン", "トートバッグ", "Tシャツ", "マグカップ",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*/?\s*袋?\s*$")
FLAVOR_LEADING_PATTERN = re.compile(r"^.*?[gｇ]\s*/\s*袋[。.！!]?\s*")


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    text = FLAVOR_LEADING_PATTERN.sub("", description)
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    title = re.sub(r"\s+", " ", title)
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = extract_flavor_notes(desc_el["content"]) if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base = TRAILING_WEIGHT_PATTERN.sub("", item["title"]).strip()
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        item = {**item, "base_name": base, "weight_g": weight_m.group(1) if weight_m else None}
        existing = by_base_name.get(base)
        existing_weight = existing["weight_g"] if existing else None
        existing_weight = int(existing_weight) if existing_weight is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"].strip()
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
    weight_g = int(item["weight_g"]) if item.get("weight_g") is not None else None

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
        "flavor_notes": item.get("flavor_notes"),
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
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append({**fields, "url": product_url})

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
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
    with open("data_tomiokacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tomiokacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
