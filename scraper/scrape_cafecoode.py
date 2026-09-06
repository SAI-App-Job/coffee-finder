# -*- coding: utf-8 -*-
"""
scrape_cafecoode.py

自家焙煎コーヒー豆 カフェコーデ(cafe-coode.jp、長野県伊那市境451-1
〈株式会社コーディネーション〉、自家焙煎豆のオンライン販売)の商品情報を
取得する。MakeShop(GMOペパボ系ECサービス、schema.org ProductGroup形式の
JSON-LD構造化データを使用。大和屋珈琲と同じ新規パターン)。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、
Disallow指定は無く実質許可。

【商品一覧の取得方法について】
実データ確認済み: 商品カテゴリは「オリジナルブレンド」「シングル
オリジン」「カフェコーデオリジナル商品」の3つがあるが、最後の
「カフェコーデオリジナル商品」はカフェオレベース・ドリップバッグ・
ギフトセットのみで構成されており焙煎豆単品が無いため巡回対象外とする。
前2カテゴリのみを巡回し、含まれる商品コード(英数字、例: B00001, S30)
へのリンクを和集合で収集する。

【商品情報の取得方法について】
実データ確認済み: 各商品ページに`<script type="application/ld+json">`
でschema.org ProductGroup構造化データが埋め込まれている。
ProductGroup.nameに重量を含む商品名、hasVariant配列に挽き方違いの
バリアント(価格は挽き方によらず同一)が入っている。

【重量違いの重複について】
実データ確認済み: 大半の銘柄が200g/500gの2サイズで個別商品登録されて
いる。商品名から末尾の重量を除いた基準名でグルーピングし、最小重量
(200g)を代表として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「ギフトケース入り」と明記されたブレンド/シングル
オリジンの詰め合わせセットが両カテゴリに混在している。
NON_BEAN_KEYWORDSで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "カフェコーデ",
    "url": "https://www.cafe-coode.jp/",
    "platform": "MakeShop",
    "address": "長野県伊那市境451-1",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため"
                          "Disallow指定は無い)",
}

BASE_URL = "https://www.cafe-coode.jp"
CATEGORY_PATHS = ["SHOP/196165/list.html", "SHOP/201325/list.html"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト"]
LD_JSON_PATTERN = re.compile(r'<script type="application/ld\+json">(\[.*?\]|\{.*?\})</script>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    codes: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select('a[href^="/SHOP/"]'):
            m = re.match(r"^/SHOP/([A-Za-z0-9]+)\.html$", a.get("href", ""))
            if m:
                codes.add(m.group(1))
    return [f"{BASE_URL}/SHOP/{code}.html" for code in codes]


def extract_product_group(html: str) -> dict | None:
    for m in LD_JSON_PATTERN.finditer(html):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if candidate.get("@type") == "ProductGroup":
                return candidate
    return None


def pick_canonical_variant_price(group: dict) -> int | None:
    variants = group.get("hasVariant") or []
    for v in variants:
        price = (v.get("offers") or {}).get("price")
        if price is not None:
            return int(float(price))
    return None


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_PATTERN.sub("", item["title"]).strip()
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = WEIGHT_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


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
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        group = extract_product_group(html)
        if not group:
            continue
        title = re.sub(r"\s+", " ", (group.get("name") or "")).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = pick_canonical_variant_price(group)
        all_items.append({"title": title, "price": price, "url": product_url})

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cafecoode.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafecoode.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
