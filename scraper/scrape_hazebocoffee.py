# -*- coding: utf-8 -*-
"""
scrape_hazebocoffee.py

Hazebo Coffee(hazebo.com、〒877-0026 大分県日田市田島本町5-33 平和ビル2F、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify。

【住所について】
特定商取引法ページ(https://hazebo.com/policies/legal-notice)で実データ
確認済み(2026-09時点): 販売業者「株式会社Alt. / Hazebo Coffee事業部」、
所在地「〒877-0026 大分県日田市田島本町5-33 平和ビル2F」との記載を確認。
候補リストの住所(平和ビル1F)とは階数が異なるが(フッターは1F表記)、他の
BASE/Shopify系スクレイパーと同様に法定表記(特定商取引法)ページの住所を
正として採用する(2F)。

robots.txt確認済み(2026-09時点): Shopify標準の記述。/checkouts/, /orders/
等の非公開ページ以外に制限は無い。

【対象商品について】
実データ確認済み(全14件、/collections/all/products.json): product_typeが
「コーヒー豆」の商品は9件あるが、うち5件は「ドリップバッグ」(単品小分け、
DB OTOKU packも含む)のため非対象。残り4件(サイアムブルームーン200g・
プリンセサワイニー200g・プレミアムショコラ200g・マンデリンビンタンリマ
200g)が実際の焙煎豆単品。他の5件(オリジナルタンブラー[雑貨]・自家製
チョリソー等[おうちバル]・放生会米[米])も非対象。

【重量について】
実データ確認済み: variants[].gramsは全商品で0(未設定)のため使用できず、
商品名末尾の「200g」等の表記から重量を取得する。

【flavor_notes(2026-09-22追記)】
実データ確認済み: body_htmlに対象4件全てで産地・精製方法・テイスティング
文が入っている。注文/配送案内等の無関係な定型文の混入は無いため全文を
そのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Hazebo Coffee",
    "url": "https://hazebo.com/",
    "platform": "Shopify",
    "address": "大分県日田市田島本町5-33 平和ビル2F",
    "prefecture": "大分県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述。/checkouts/, "
                          "/orders/等の非公開ページ以外に制限は無い)",
}

PRODUCTS_JSON_URL = "https://hazebo.com/collections/all/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "OTOKU pack", "pack"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*$")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json().get("products", [])


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def extract_flavor_notes(body_html: str) -> str | None:
    text = BeautifulSoup(body_html or "", "html.parser").get_text("\n", strip=True)
    return text or None


def build_record(product: dict) -> dict | None:
    if (product.get("product_type") or "").strip() != "コーヒー豆":
        return None

    raw_title = (product.get("title") or "").strip()
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None
    if not WEIGHT_PATTERN.search(raw_title):
        # 重量表記の無い商品(ドリップバッグ単品等)は対象外
        return None

    title, weight_g = base_name_and_weight(raw_title)
    if not title:
        return None

    variants = product.get("variants") or []
    variant = variants[0] if variants else {}
    price = int(float(variant["price"])) if variant.get("price") else None
    product_url = f"https://hazebo.com/products/{product.get('handle')}"

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
    with open("data_hazebocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hazebocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
