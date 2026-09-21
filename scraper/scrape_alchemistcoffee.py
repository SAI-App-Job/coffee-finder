# -*- coding: utf-8 -*-
"""
scrape_alchemistcoffee.py

宮の森アルケミストコーヒー(alchemist-coffee.com、札幌市中央区宮の森3条13丁目
5-18、Wix)の商品情報を取得する。KATARU COFFEE(scrape_katarucoffee.py)と
同じくWix Storesのstore-products-sitemap.xml + JSON-LDのProduct構造化
データ方式。

住所はJSON-LD(LocalBusiness)で実データ確認済み(2026-09時点、postalCode
064-0953、streetAddress「中央区宮の森3条13丁目5-18」)。候補リストでは
プラットフォームが「custom」とされていたが、実際はWixだった。

【対象商品について】
実データ確認済み(sitemap全7件): コーヒー豆単品6件(コスタリカ・ブラジル
(2種)・インドネシア・エスプレッソブレンド・コロンビア、いずれも1kg)と、
「水出しコーヒーボトル ハリオ カークボトル 1,000ml」(器具、コーヒー豆
ではない)。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): User-agent: *にAllow: /(lightboxクエリの
み除外)、PetalBotのみ全面Disallow。一般クローラーへの制限なし。

【flavor_notes(2026-09-21追記)】
実データ確認済み: JSON-LD Productのdescriptionフィールドに対象6件全てで
テイスティング文が入っている。先頭に「【今すぐご注文で、送料無料】」と
いう販促文が付く場合、末尾に「*.....お豆の生産地、カッピングコメント
など情報詳細が記載がされた特別カード付き」という同梱カードの案内が
付く場合があるため、それぞれ除去する。
"""

import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "宮の森アルケミストコーヒー",
    "url": "https://www.alchemist-coffee.com/",
    "platform": "Wix",
    "address": "北海道札幌市中央区宮の森3条13丁目5-18",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。User-agent: *にAllow: /"
                          "[lightboxクエリのみ除外]。PetalBotのみ全面Disallow)",
}

BASE_URL = "https://www.alchemist-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ボトル", "ハリオ"]
WEIGHT_PATTERN_KG = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE)
WEIGHT_PATTERN_G = re.compile(r"(\d+)\s*[gｇ]")
JSONLD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
FLAVOR_LEADING_PATTERN = re.compile(r"^【今すぐご注文で、送料無料】\s*")
FLAVOR_STOP_PATTERN = re.compile(r"\*\.+お豆の生産地")


def fetch_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def extract_product_jsonld(html: str) -> dict | None:
    for match in JSONLD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN_KG.search(title)
    if m:
        return int(float(m.group(1)) * 1000)
    m = WEIGHT_PATTERN_G.search(title)
    return int(m.group(1)) if m else None


def build_record(product_url: str, data: dict) -> dict | None:
    title = (data.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    offers = data.get("offers") or {}
    price = None
    if offers.get("price") is not None:
        try:
            price = int(float(offers["price"]))
        except (TypeError, ValueError):
            price = None
    availability = (offers.get("availability") or "").rstrip("/").split("/")[-1]
    structural_out_of_stock = availability not in ("InStock", "")

    parsed = parse_product(title)

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

    weight_g = parse_weight_g(title)
    stock_status = detect_stock_status(title, structural_out_of_stock)

    flavor_notes = (data.get("description") or "").strip()
    flavor_notes = FLAVOR_LEADING_PATTERN.sub("", flavor_notes)
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()]
    flavor_notes = flavor_notes.strip() or None

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
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        data = extract_product_jsonld(resp.text)
        if not data:
            continue
        detail = build_record(product_url, data)
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
    with open("data_alchemistcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_alchemistcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
