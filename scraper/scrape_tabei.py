# -*- coding: utf-8 -*-
"""
scrape_tabei.py

TABEI COFFEE(tabei-coffee.com、千葉県四街道市、店主自ら世界11カ国の
農園を訪問して選定した豆を自家焙煎)の商品情報を取得する。WordPress +
Welcart(フォレスト自家焙煎コーヒー豆店と同じプラットフォーム)。

robots.txt確認済み(2026-09時点): /wp-admin/以外は制限なし
(標準的なWordPress設定、admin-ajax.phpのみAllow指定あり)。

【商品一覧の取得方法について】
実データ確認済み: オンラインショップページ(/online-shop/)は1ページに
全商品(24件)が「COFFEE GIFT」「COFFEE」(NEW ARRIVAL/浅煎り＆中煎り/
深煎り)「DRIP COFFEE」「OTHERS」の見出しで区切って表示される構造
(ページネーション無し)。コーヒー豆単品が並ぶのは「COFFEE」セクション
(h3見出し)のみで、「COFFEE GIFT」は複数商品の詰め合わせ、「DRIP
COFFEE」はドリップバッグ、「OTHERS」はCOE入賞豆(完売)・水出し
アイスパックで、豆売り単品の一覧としては「COFFEE」セクションが対象。
「COFFEE」内の13件のうち「C01 スイートセット」のみ複数銘柄の
詰め合わせセットのためNON_BEAN_KEYWORDSで除外し、残り12件が対象。

【価格・重量について】
実データ確認済み: 商品詳細ページは複数の重量帯(100g/200g/400g等)が
`div.field[itemprop="offers"]`としてSKUごとに個別に構造化されており、
各SKU内の`span.skudisp`(例:「100g袋入」)とitemprop="price"のspan
(例:「¥1,296」)から重量・価格を取得できる。最小重量のSKUを代表価格として
採用する(他のWelcart店舗フォレスト自家焙煎コーヒー豆店と同じ「デフォルト
=最小重量」方針)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "TABEI COFFEE",
    "url": "https://tabei-coffee.com/",
    "platform": "WordPress + Welcart",
    "address": "千葉県四街道市",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-09確認。/wp-admin/以外は制限なし、標準的なWordPress設定)",
}

BASE_URL = "https://tabei-coffee.com"
LIST_URL = f"{BASE_URL}/online-shop/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_coffee_section_list() -> list[dict]:
    soup = fetch_page(LIST_URL)

    coffee_heading = None
    for h3 in soup.select("h3"):
        if h3.get_text(strip=True) == "COFFEE":
            coffee_heading = h3
            break
    if coffee_heading is None:
        return []

    results = []
    for sibling in coffee_heading.find_all_next():
        if sibling.name == "h3":
            break
        if sibling.name == "a" and "item_block_list" in (sibling.get("class") or []):
            title_el = sibling.select_one("li.item_name h4")
            if not title_el:
                continue
            # h4は<span>商品コード(N01等)</span>商品名という構造(実データ確認済み)。
            # spanを除去しないとget_text()で「N01ペルー...」のように商品コードが
            # 商品名に隙間なく連結されてしまうため、spanを取り除いてから抽出する。
            code_span = title_el.select_one("span")
            if code_span:
                code_span.decompose()
            title = title_el.get_text(strip=True)
            product_url = sibling.get("href", "")
            results.append({"raw_name": title, "product_url": product_url})
    return results


def parse_product_detail(url: str, list_title: str) -> dict | None:
    soup = fetch_page(url)

    if any(kw in list_title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(list_title)

    offers = soup.select('div.field[itemprop="offers"]')
    skus = []
    for offer in offers:
        price_el = offer.select_one('span.price[itemprop="price"]')
        weight_el = offer.select_one("span.skudisp")
        availability_el = offer.select_one('meta[itemprop="availability"]')
        if not price_el:
            continue
        price_match = PRICE_PATTERN.search(price_el.get_text())
        price = int(price_match.group(1).replace(",", "")) if price_match else None
        weight_text = weight_el.get_text(strip=True) if weight_el else ""
        weight_match = WEIGHT_PATTERN.search(weight_text)
        weight_g = int(weight_match.group(1)) if weight_match else None
        availability = (availability_el.get("content") or "") if availability_el else ""
        skus.append({"price": price, "weight_g": weight_g, "availability": availability})

    canonical = min(
        (s for s in skus if s["weight_g"] is not None),
        key=lambda s: s["weight_g"],
        default=(skus[0] if skus else None),
    )

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": list_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": canonical["price"] if canonical else None,
            "product_url": url,
        }

    structural_out_of_stock = bool(skus) and all(
        "在庫有り" not in s["availability"] for s in skus
    )
    stock_status = detect_stock_status(list_title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": list_title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": canonical["price"] if canonical else None,
        "weight_g": canonical["weight_g"] if canonical else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_coffee_section_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            continue
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"], item["raw_name"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue

        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        items = scrape_coffee_section_list()
        match = next((i for i in items if i["product_url"] == url), None)
        title = match["raw_name"] if match else ""
        print(json.dumps(parse_product_detail(url, title), ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_tabei.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_tabei.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
