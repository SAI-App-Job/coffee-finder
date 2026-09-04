# -*- coding: utf-8 -*-
"""
scrape_hitsuji.py

ひつじ珈琲(hitsuji-coffee.com、栃木県大田原市中野内735〈焙煎所本店〉、
自家焙煎豆のオンライン販売)の商品情報を取得する。WordPress+WooCommerce。
本プロジェクトで初めてのWooCommerce店舗。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/等の管理
系パスのみDisallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う
公開APIエンドポイント(/wp-json/wc/store/v1/products)は制限対象外。

【商品情報の取得方法について】
実データ確認済み: WooCommerceブロックカート機能が使う公開REST API
(認証不要)`/wp-json/wc/store/v1/products`から全80件を1リクエストで
取得できる。各商品のshort_description(HTML)に「【焙煎度】」
「【内容量】」の構造化された記述があり、内容量から重量(g)を、
焙煎度から括弧内の日本語表記を抽出する。価格はprices.price
(税込・円単位の整数文字列)をそのまま使う。

【非コーヒー豆商品の除外について】
実データ確認済み: 全80件中、答弁トートバッグ/巾着/Tシャツ/ステッカー/
缶バッジ/マグカップ/クッキー缶/ラテボウル/グラス/キャニスター缶/
ダイナーマグ/キャンバス(インテリア)等の雑貨、CAFEC器具、Ring(指輪)、
アガベチタノタ(観葉植物)、ドリップパック/ギフト各種(既存銘柄の詰め
合わせ)、ラテベース(液体)、シュガー、ラバーバンド、「コーヒー
マイスターセレクト20g×12種」(試飲用アソート)、「個人決済用」(店頭
決済用の非公開個別請求)がコーヒー豆単品ではないためNON_BEAN_KEYWORDS
で除外する。
"""

import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ひつじ珈琲",
    "url": "https://hitsuji-coffee.com/",
    "platform": "WooCommerce",
    "address": "栃木県大田原市中野内735",
    "prefecture": "栃木県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等の管理系パスのみ"
                          "Disallow。本スクレイパーが使うStore API"
                          "(/wp-json/wc/store/v1/products)は制限対象外)",
}

API_URL = "https://hitsuji-coffee.com/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ポーチ", "マルチケース", "トートバッグ", "巾着", "Tシャツ", "ステッカー", "缶バッジ",
    "マグカップ", "クッキー缶", "ラテボウル", "オリジナルグラス", "キャニスター缶",
    "ダイナーマグ", "キャンバス", "パンペルデュラスク", "ドリップパック", "ラテベース",
    "シュガー", "美濃焼", "SIMPLIFY", "CAFEC", "Ring｜", "個人決済用",
    "コーヒーマイスターセレクト", "アガベチタノタ", "ギフト", "ラバーバンド",
]
WEIGHT_PATTERN = re.compile(r"内容量[】\]]\s*(\d+)\s*[gｇ㌘]|(\d+)\s*[kKｋＫ][gｇ]|(\d+)\s*㎏|(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"焙煎度[^（(]*[（(]([^）)]+)[）)]")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return HTML_TAG_PATTERN.sub(" ", text or "")


def parse_weight_g(name: str, description: str) -> int | None:
    text = f"{description} {name}"
    m = re.search(r"内容量[】\]]\s*(\d+)\s*[gｇ㌘]", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*[kKｋＫ][gｇ]|(\d+)\s*㎏", name)
    if m:
        num = next(g for g in m.groups() if g is not None)
        return int(num) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", name)
    if m:
        return int(m.group(1))
    return None


def build_record(product: dict) -> dict | None:
    name = (product.get("name") or "").strip()
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    description = strip_html(product.get("short_description") or "")
    roast_m = ROAST_PATTERN.search(description)
    roast_text = roast_m.group(1).strip() if roast_m else ""
    raw_name = f"{name} {roast_text}".strip() if roast_text else name

    parsed = parse_product(raw_name)
    price = product.get("prices", {}).get("price")
    price = int(price) if price is not None else None
    product_url = product.get("permalink")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = not product.get("is_in_stock", True)
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)
    weight_g = parse_weight_g(name, description)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
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


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_hitsuji.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hitsuji.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
