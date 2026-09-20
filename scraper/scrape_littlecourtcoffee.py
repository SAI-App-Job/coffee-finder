# -*- coding: utf-8 -*-
"""
scrape_littlecourtcoffee.py

Little Court Coffee(littlecourtcoffee.com、島根県松江市片原町104、自家焙煎豆
のオンライン販売)の商品情報を取得する。Shopify(/products.json全件取得方式)。

【住所について】
公式ストアの特定商取引法ページ(https://littlecourtcoffee.com/policies/
legal-notice)で実データ確認済み(2026-09時点): 「LITTLE COURT COFFEE 代表責任者
長谷川卓 / 所在地　〒690-0847 島根県松江市片原町104」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): Shopify標準の記述で、"Public product,
collection, page, blog, policy, cart, and localized HTML is crawlable"と明記。
本スクレイパーは対象。

【商品名の構成について】
実データ確認済み: 商品名は「焙煎度/産地or国/銘柄」の構成(例:
「中深煎り/ケニア/カンゴチョAA」)。coffee_parserは全角スラッシュ区切りを
特別扱いしないが、国名キーワード自体は文中のどこにあっても検出できるため、
そのまま渡してもorigin_country検出に問題は無い。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全35件): product_typeが「コーヒー」以外
(「器具・雑貨」、V60ペーパーフィルター等)は非対象。「コーヒー」type内でも
【GIFT】箱入アイスリキッドコーヒー各種・ギフトセット各種・ドリップバッグ
５個セット・アイスリキッドコーヒー各種(瓶入り完成品、リキッド)は
NON_BEAN_KEYWORDSで除外する。残り15件(いずれも産地or ブレンド名を持つ
焙煎豆単品)を対象とする。

【重量について】
実データ確認済み: 各商品のvariantsは「豆/100g/宅急便」のように挽き方・重量・
配送方法の組み合わせで構成され、価格は挽き方・配送方法に依らずgrams共通。
option1が「豆」(挽かない全粒)のバリアントを代表として採用し、
そのgramsフィールドを重量として使う。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlの最初の<p>に産地の背景ストーリーとテイス
ティング表現が地続きで入っており(対象15件全てで確認)、末尾に
「----」区切りの構造化欄(国/銘柄/焙煎度)、続けて別の<p>に「風味…」
という短いフレーバー記述語+苦味/酸味/甘味の■□ドット評価+標高/品種/
精製のスペック欄が入る。最初の<p>全文と、「風味…」ラベル以降の記述語
のみを結合して採用し、構造化欄・ドット評価・スペック行は除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Little Court Coffee",
    "url": "https://littlecourtcoffee.com/",
    "platform": "Shopify",
    "address": "島根県松江市片原町104",
    "prefecture": "島根県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述で\"Public product, "
                          "collection, page, blog, policy, cart, and localized "
                          "HTML is crawlable\"と明記)",
}

PRODUCTS_JSON_URL = "https://littlecourtcoffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BEAN_PRODUCT_TYPE = "コーヒー"
NON_BEAN_KEYWORDS = ["GIFT", "ギフト", "セット", "リキッド"]
FLAVOR_LINE_PATTERN = re.compile(r"風味[…\.]+([^\n]+)")


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    paragraphs = [p.get_text() for p in soup.find_all("p")]
    if not paragraphs:
        return None
    main = paragraphs[0].strip()

    descriptor = None
    for p in paragraphs[1:]:
        m = FLAVOR_LINE_PATTERN.search(p)
        if m:
            descriptor = m.group(1).strip()
            break

    parts = [p for p in [main, descriptor] if p]
    return "\n".join(parts) if parts else None


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(product: dict, title: str) -> bool:
    if product.get("product_type") != BEAN_PRODUCT_TYPE:
        return True
    return any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS)


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if (v.get("option1") or "") == "豆"]
    pool = whole_bean or variants
    return pool[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or is_excluded(product, title):
        return None

    parsed = parse_product(title)
    product_url = f"https://littlecourtcoffee.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
    weight_g = variant.get("grams") if variant and variant.get("grams") else None

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

    all_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
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
        "flavor_notes": extract_flavor_notes(product.get("body_html")),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_littlecourtcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_littlecourtcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
