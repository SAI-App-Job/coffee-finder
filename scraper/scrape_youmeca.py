# -*- coding: utf-8 -*-
"""
scrape_youmeca.py

YOUMECA(スペシャルティコーヒー豆、cafec.shop、〒874-0921 大分県別府市富士見町
6番30号、自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify。

【店舗の実態について(候補リストの注記への対応)】
候補リストでは「cafec.shopがYOUMECA自身の正規販売アカウントか、誤って
第三者プラットフォームとラベル付けされていないか要確認」との注記があった。
実データ確認の結果、cafec.shopはコーヒー器具ブランド「CAFEC」を展開する
株式会社三洋産業の公式ECサイトであり(フッター「&copy;SANYOSANGYO CAFEC
All Rights Reserved」)、CAFEC製品と自社のスペシャルティコーヒー豆ブランド
「YOUMECA」を同一サイト内で販売している。三洋産業の本社所在地は大分県
別府市富士見町6-30(公式サイト外の会社概要ページ・ニュースリリースで確認)
であり、候補リストの住所と一致することを確認した。第三者プラットフォームの
誤ラベルではなく、YOUMECAブランドを展開する三洋産業自身の公式ストアである。

robots.txt確認済み(2026-09時点): Shopify標準の記述("Shopify storefront.
Public product, collection, page, blog, policy, cart, and localized HTML
is crawlable")。/products/, /collections/等への制限は無い。

【商品データの取得方法について】
実データ確認済み: collections/coffee-beans(コーヒー豆、ストレート+ブレンド
両方を含む)のproducts.jsonから全20件を取得できる。product_typeが
「コーヒー豆＞ストレート」または「コーヒー豆＞ブレンド」の商品のみを対象と
し、以下は除外する。
・「YOUMECA スペシャリティコーヒー2袋ギフト」「4袋ギフト」
  (product_type: コーヒー豆＞セット商品、複数銘柄の詰め合わせギフト)
・「DEEP27 スターターセット」(product_type: コーヒー豆のみだが実際は
  ドリッパー器具のスターターセットで焙煎豆ではない)
CAFEC製のドリッパー・フィルター・ケトル・ミル・サーバー等の器具や、
ドリップコーヒー・コーヒー飲料(リキッド・カフェオレベース・水出しバッグ)・
スイーツ・その他のギフト/セットは、コーヒー豆コレクション自体に含まれない
ため自然に対象外となる。

【重量について】
実データ確認済み: 対象13件は全て「(200g)」を商品名に含む単一サイズ。
挽き方違い(そのまま/中挽き/中細挽き/細挽き/極細挽き)のバリアントが同一
価格で並ぶため、先頭バリアントの価格を代表として採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: products.jsonのbody_htmlにテイスティング文・産地
スペック情報・「▼フレーバー」欄・農園の背景ストーリーが一体となった
説明が入っている(対象17件中16件で確認、価格・配送等の混入なし)。
HTMLタグを除去した全文を採用する。1件(匠takumi-中塚社長ブレンド)は
「ドリップコーヒーはこちらから」という外部リンク案内文のみで、
テイスティング文が存在しなかった(genuineな欠落、句点「。」を含む
文が無いことを簡易的な判定基準として除外する)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "YOUMECA",
    "url": "https://cafec.shop/",
    "platform": "Shopify",
    "address": "大分県別府市富士見町6番30号",
    "prefecture": "大分県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述。products/"
                          "collections等への制限は無い)",
}

PRODUCTS_JSON_URL = "https://cafec.shop/collections/coffee-beans/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDED_HANDLES = {"deep27set"}
VALID_PRODUCT_TYPES = {"コーヒー豆>ストレート", "コーヒー豆>ブレンド"}
WEIGHT_PATTERN = re.compile(r"[（(](\d+)\s*[gｇ][）)]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*[（(]\s*\d+\s*[gｇ]\s*[）)]\s*$")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json().get("products", [])


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not body_html:
        return None
    soup = BeautifulSoup(body_html, "html.parser")
    lines = [line.strip() for line in soup.get_text("\n").split("\n") if line.strip()]
    text = "\n".join(lines).strip()
    if "。" not in text:
        return None
    return text or None


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(product: dict) -> dict | None:
    handle = product.get("handle", "")
    if handle in EXCLUDED_HANDLES:
        return None
    product_type = (product.get("product_type") or "").strip()
    if product_type not in VALID_PRODUCT_TYPES:
        return None

    raw_title = (product.get("title") or "").strip()
    if not raw_title:
        return None
    title, weight_g = base_name_and_weight(raw_title)
    if not title:
        return None

    variants = product.get("variants") or []
    variant = variants[0] if variants else {}
    price = int(float(variant["price"])) if variant.get("price") else None
    product_url = f"https://cafec.shop/products/{handle}"

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
    with open("data_youmeca.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_youmeca.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
