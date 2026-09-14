# -*- coding: utf-8 -*-
"""
scrape_matsurica.py

松本珈琲店 まつりか(matsurica1978.jp、宮城県仙台市青葉区立町22-14 西公園マンション1F、
自家焙煎豆のオンライン販売。1978年創業)の商品情報を取得する。MakeShop。

【住所について】
公式サイトの特定商取引法ページ(https://matsurica1978.jp/html/ordercontract.html)で
実データ確認(2026-09時点): 〒980-0822 宮城県仙台市青葉区立町22-14 西公園マンション1F。

robots.txt確認済み(2026-09時点): https://matsurica1978.jp/robots.txtはカスタム404
ページが返る(実質存在しない)。クロール制限の記述が無いため実質無制限と判断した
(1518coffee等と同一の状況)。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点): /shopbrand/all_items/ページ1ページのみで全41件の
shopdetailリンクが揃っており(id="000000000001"〜"000000000070"、一部欠番)、
ページネーションのリンクも存在しない。1ページの取得で全件を網羅できる。

【価格の取得方法について】
実データ確認済み: 商品詳細ページのspan#price2_valueに税込価格がそのまま入っている
(1518coffee等のinput要素のvalue属性から取る形式とは異なり、テキストノードとして
直接埋め込まれている)。

【商品名・重量について】
実データ確認済み: 商品名に重量(100g等)が末尾に含まれる(例:「マスターブレンド
中深煎り 100g」)。産地情報の構造化された説明欄は無く、商品名のみから
coffee_parser.parse_product()で産地・焙煎度等を判定する。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "松本珈琲店 まつりか",
    "url": "https://matsurica1978.jp/",
    "platform": "MakeShop",
    "address": "宮城県仙台市青葉区立町22-14 西公園マンション1F",
    "prefecture": "宮城県",
    "robots_txt_status": "実質無制限(2026-09確認。robots.txtはカスタム404ページが返り、"
                          "実質的な制限記述が無い。1518coffee等と同一の状況)",
}

BASE_URL = "https://matsurica1978.jp"
LIST_URL = f"{BASE_URL}/shopbrand/all_items/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

DETAIL_ID_PATTERN = re.compile(r"/shopdetail/([0-9]{12})/")
NAME_PATTERN = re.compile(r"商品名\s*[:：]\s*(.+)")
PRICE_PATTERN = re.compile(r'id="price2_value"[^>]*>([\d,]+)<')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# 実データ確認済み(2026-09時点): 41件全件がストレート/ブレンドの焙煎豆で、
# ドリップバッグ・器具等の非対象商品は見当たらなかった


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_ids() -> list[str]:
    soup = fetch_page(LIST_URL)
    ids: list[str] = []
    seen = set()
    for a in soup.select('a[href*="/shopdetail/"]'):
        m = DETAIL_ID_PATTERN.search(a.get("href", ""))
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            ids.append(m.group(1))
    return ids


def extract_fields(soup: BeautifulSoup) -> dict | None:
    text = soup.get_text("\n")
    name_m = NAME_PATTERN.search(text)
    if not name_m:
        return None
    title = unicodedata.normalize("NFKC", name_m.group(1).strip())

    price_m = PRICE_PATTERN.search(str(soup))
    price = int(price_m.group(1).replace(",", "")) if price_m else None

    return {"title": title, "price": price}


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "weight_g": weight_g,
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)

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
    product_ids = fetch_product_ids()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_id in product_ids:
        product_url = f"{BASE_URL}/shopdetail/{product_id}/all_items/page1/order/"
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=fields["title"], price=fields.get("price")):
            records.append(prev)
            continue

        detail = build_record({**fields, "url": product_url})
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
    with open("data_matsurica.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsurica.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
