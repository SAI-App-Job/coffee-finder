# -*- coding: utf-8 -*-
"""
scrape_enjoycoffee.py

共和コーヒー店(今日は珈琲、enjoy-coffee.com、愛知県名古屋市中川区舟戸町
4-21、自家焙煎豆のオンライン販売。6店舗を展開する株式会社共和コーヒー店
の直営通販サイト)の商品情報を取得する。MakeShop(schema.org ProductGroup
形式のJSON-LD構造化データを使用。カフェコーデと同じ新規パターン)。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、
Disallow指定は無く実質許可。

【商品一覧の取得方法について】
実データ確認済み: 「コーヒー豆一覧」カテゴリ(SHOP/73139/list.html、
ストレート・ブレンド・炭焼シリーズ・デカフェ・アイスコーヒー用細挽き等
を横断的に含む、全59件)を2ページ(list.html・t01/list2.html)巡回して
個別商品ページへのリンクを収集する。カフェオレベース・水出しコーヒー
パック等の他カテゴリ(ホームページの特集枠に別途表示)は本カテゴリに
含まれないため巡回対象外。

【非コーヒー豆商品の除外について】
実データ確認済み: 全59件のうち「簡単オーダー表　100g×3種類」(kantan-
order300g.html、3種類を自由に組み合わせる注文フォームで単一銘柄を
指し示さないため)が非対象。NON_BEAN_KEYWORDSで除外する。「プレミアム・
アイスコーヒー」「炭焼きアイスコーヒー(アイス用細挽)」「カフェインレス
ブレンド・アイスコーヒー(細挽き)」は商品説明から水出し用に細挽きされた
焙煎豆(粉)であることを確認済みのため対象に含める(瓶入り等の完成品
ドリンクではない)。

【重量違いの重複について】
実データ確認済み: 全商品が単一のMakeShop商品(ProductGroup)内に100g/
200g/300g/400g/500g/1kgの重量バリエーションをhasVariantとして持つ
(商品自体が重量ごとに分かれてはいない)。価格は重量に比例する。各
バリアントのnameが末尾に"/100g"のように重量を含むため、そこから正規
表現で重量を抽出し、在庫があるバリアントの中から最小重量を代表として
採用する(全滅時は在庫の有無を問わず全体から最小重量を採用)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "共和コーヒー店(今日は珈琲)",
    "url": "https://www.enjoy-coffee.com/",
    "platform": "MakeShop",
    "address": "愛知県名古屋市中川区舟戸町4-21",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため"
                          "Disallow指定は無い)",
}

BASE_URL = "https://www.enjoy-coffee.com"
CATEGORY_PATHS = ["SHOP/73139/list.html", "SHOP/73139/t01/list2.html"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["簡単オーダー"]
LD_JSON_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"/(\d+)\s*(kg|[gｇ])$", re.IGNORECASE)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    paths: set[str] = set()
    for category_path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{category_path}")
        for a in soup.select('a[href^="/SHOP/"]'):
            href = a.get("href", "")
            m = re.match(r"^/SHOP/([A-Za-z0-9_-]+)\.html$", href)
            if m and "list" not in m.group(1):
                paths.add(m.group(1))
    return [f"{BASE_URL}/SHOP/{code}.html" for code in sorted(paths)]


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


def variant_weight_g(variant: dict) -> int | None:
    name = variant.get("name") or ""
    m = WEIGHT_PATTERN.search(name)
    if not m:
        return None
    value = int(m.group(1))
    return value * 1000 if m.group(2).lower() == "kg" else value


def pick_canonical_variant(variants: list[dict]) -> tuple[dict | None, int | None]:
    def is_available(v):
        return (v.get("offers") or {}).get("availability") == "http://schema.org/InStock"

    def weight_key(v):
        w = variant_weight_g(v)
        return w if w is not None else float("inf")

    available = [v for v in variants if is_available(v)]
    pool = available or variants
    if not pool:
        return None, None
    variant = min(pool, key=weight_key)
    weight = variant_weight_g(variant)
    return variant, weight


def build_record(group: dict, product_url: str) -> dict | None:
    title = re.sub(r"\s+", " ", (group.get("name") or "")).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    variants = group.get("hasVariant") or []
    variant, weight_g = pick_canonical_variant(variants)
    price = None
    if variant:
        raw_price = (variant.get("offers") or {}).get("price")
        price = int(float(raw_price)) if raw_price is not None else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    all_out_of_stock = bool(variants) and not any(
        (v.get("offers") or {}).get("availability") == "http://schema.org/InStock" for v in variants
    )
    stock_status = detect_stock_status(title, all_out_of_stock)

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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
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
        detail = build_record(group, product_url)
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
    with open("data_enjoycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_enjoycoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
