# -*- coding: utf-8 -*-
"""
scrape_nageiacoffee.py

nageia coffee(nageia-coffee.com、878-0012 大分県竹田市竹田町563-1、自家焙煎
豆のオンライン販売)の商品情報を取得する。Shopify。

robots.txt確認済み(2026-09時点): 一般的なShopifyの標準的な記述で、User-agent: *
に対する明示的な制限は無い(/checkouts/, /orders/等の非公開ページのみ
Disallow)。本スクレイパーが対象とする商品ページ・products.jsonへの制限は無い。

【住所について】
特定商取引法ページ(https://nageia-coffee.com/pages/legal-notice、実際は
サイト内リンクから確認)で実データ確認済み(2026-09時点): 所在地「878-0012,
大分県 竹田市 竹田市竹田町563-1」との記載を確認。候補リストの住所と一致。

【商品データの取得方法について】
実データ確認済み: Shopify標準の/collections/all/products.json(?limit=250)
から全14件を取得できる。product_typeが「coffee beans」の商品のうち、以下は
非対象として除外する。
・nageia-collection「nageia 3beans set」: 複数銘柄の詰め合わせセット(80g×3)
・gift-box「ギフトボックス」: 箱代のみの追加オプション商品(¥50)
・cold-brew-coffee-bags-*「水出しコーヒーバッグ」: 水出し用バッグ(粉小分け)
・コーヒーの定期便(コーヒーsubscription): 定期購入
また「nagi｜music for nageia coffee」はproduct_typeが空でそもそも楽曲(音楽)
商品のため対象外。「ドリップバッグ10個」「dripu(ドリップバッグ5セット)」も
ドリップバッグのため除外する。
残り7件(ストレート6種+シーズナルブレンド「カーム」1種)が対象。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlに対象7件全てでテイスティング文・産地紹介
(インポーター資料からの引用を含む)が入っている。末尾に3個以上のハイフン
から成る区切り線があり、その後に発送/保存方法の定型文が続くため、この
区切り線の直前で打ち切る。

【重量・在庫について】
実データ確認済み: 対象7件は全て200g/400g(200g×2袋・5%OFF)の2種類の重量が
バリアントとして存在し、さらに挽き方(豆のまま/ペーパーフィルター用/
フレンチプレス用)違いが同一重量・同一価格で並ぶ。最小重量(200g)のバリアント
代表価格を採用する。商品名に含まれる「【sold out】」「【New!】」等の接頭辞は
在庫状況を示す運営者側の注記のため、raw_nameからは除去したうえで、Shopify
バリアントのavailableフラグ(いずれかのバリアントが購入可能かどうか)を
detect_stock_statusの構造的判定に渡す。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "nageia coffee",
    "url": "https://nageia-coffee.com/",
    "platform": "Shopify",
    "address": "大分県竹田市竹田町563-1",
    "prefecture": "大分県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述。/checkouts/, "
                          "/orders/等の非公開ページ以外に制限は無い)",
}

PRODUCTS_JSON_URL = "https://nageia-coffee.com/collections/all/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDED_HANDLES = {
    "nageia-collection",  # 3beans set(詰め合わせ)
    "gift-box",  # ギフトボックス(箱代のみ)
}
NON_BEAN_KEYWORDS = ["music", "ドリップバッグ", "水出し", "定期便", "subscription", "コーヒーの"]
TAG_PATTERN = re.compile(r"[【\[](?:sold out|Sold out|New!?|売り切れ次第終了)[】\]]", re.IGNORECASE)
FLAVOR_STOP_PATTERN = re.compile(r"-{3,}")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json().get("products", [])


def extract_flavor_notes(body_html: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text("\n", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()]
    return text.strip() or None


def pick_min_weight_variant(variants: list[dict]) -> dict | None:
    priced = [v for v in variants if v.get("grams")]
    pool = priced or variants
    if not pool:
        return None
    return min(pool, key=lambda v: v.get("grams") or float("inf"))


def build_record(product: dict) -> dict | None:
    handle = product.get("handle", "")
    if handle in EXCLUDED_HANDLES:
        return None
    if (product.get("product_type") or "").strip().lower() != "coffee beans":
        return None

    raw_title = (product.get("title") or "").strip()
    title = TAG_PATTERN.sub("", raw_title).strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw.lower() in raw_title.lower() for kw in NON_BEAN_KEYWORDS):
        return None

    variants = product.get("variants") or []
    variant = pick_min_weight_variant(variants)
    if not variant:
        return None
    price = int(float(variant["price"])) if variant.get("price") else None
    weight_g = variant.get("grams") or None
    product_url = f"https://nageia-coffee.com/products/{handle}"

    parsed = parse_product(title)

    any_available = any(v.get("available") for v in variants)

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

    stock_status = detect_stock_status(title, not any_available)

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
    with open("data_nageiacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nageiacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
