# -*- coding: utf-8 -*-
"""
scrape_itsuki.py

ITSUKI Coffee Roastery(itsuki-coffee.net、東京都中野区)の商品情報を取得する。
WooCommerce(WordPress用ECプラグイン)というこのプロジェクト初対応の
プラットフォーム。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/のみDisallow
(admin-ajax.phpは例外的にAllow)。それ以外は制限なし。

【カタログ規模について】
実データ確認済み(2026-09時点): 商品カテゴリは「コーヒー豆」1つのみで、
掲載商品も3件のみ(ブラジル　アマレロブルボン／スマトラ　マンデリン／
エチオピア　イルガチェフェ)。/products/coffee-beans/page/2/は存在する
ものの中身が空(WordPress側の仕様上ページリンク自体は生成されるが商品0件)
であることを確認済みで、3件が実際の全商品数。

【商品説明文が存在しない点について】
実データ確認済み(3件全件): JSON-LDのdescriptionフィールドが空文字列で、
商品詳細ページ本体にも商品説明・産地情報等のテキストコンテンツが一切無い
(価格・重量バリエーションの選択肢と「カートに入れる」ボタンのみ)。そのため
産地・精選方法・グレード等はすべて商品名からcoffee_parser.parse_product()
で判定する(例:「スマトラ　マンデリン」→特定銘柄判定でインドネシア)。

【重量・価格バリエーションについて】
実データ確認済み: WooCommerceの標準的な変動商品(variable product)で、
商品詳細ページのフォームにdata-product_variations属性としてJSON形式で
複数の重量(グラム)ごとの価格が埋め込まれている(例:
[{"attributes":{"attribute_pa_gram":"600g"},"display_price":3600,...},
{"attributes":{"attribute_pa_gram":"400g"},"display_price":2500,...},
{"attributes":{"attribute_pa_gram":"200g"},"display_price":1300,...}])。
これをJSONとしてパースし、最小重量(200g)のバリエーションを代表として
price/weight_gに採用する(WOODBERRY COFFEEのpick_canonical_variant()と
同じ考え方)。

【在庫状態について】
実データ確認済み: JSON-LDのofferの各バリエーションはis_in_stock=true。
全バリエーションがfalseの場合のみ一時的な品切れとして扱う。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ITSUKI Coffee Roastery",
    "url": "https://itsuki-coffee.net/",
    "platform": "WordPress + WooCommerce",
    "address": "東京都中野区",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *に対し/wp-admin/のみDisallow"
                          "(admin-ajax.phpは例外的にAllow)。それ以外は制限なし)",
}

BASE_URL = "https://itsuki-coffee.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

GRAM_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/products/coffee-beans/")
    results = []
    seen_urls = set()
    for card in soup.select("article.c-item"):
        link_el = card.select_one("a.c-item__link")
        title_el = card.select_one("h3.c-item__ttl")
        if not link_el or not title_el:
            continue
        product_url = link_el.get("href", "")
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url})
    return results


def pick_canonical_variant(variations: list[dict]) -> dict | None:
    """在庫のあるバリエーションの中から最小重量のものを選ぶ。理由は
    モジュールdocstring参照。"""
    if not variations:
        return None
    in_stock = [v for v in variations if v.get("is_in_stock")]
    pool = in_stock or variations

    def sort_key(v):
        m = GRAM_PATTERN.search(v.get("attributes", {}).get("attribute_pa_gram", ""))
        return int(m.group(1)) if m else float("inf")

    return min(pool, key=sort_key)


def build_record(soup: BeautifulSoup, product_url: str, fallback_title: str) -> dict:
    title_el = soup.select_one("h1.product_title")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    variations = []
    form_el = soup.select_one("form.variations_form")
    raw_variations = form_el.get("data-product_variations") if form_el else None
    if raw_variations:
        try:
            variations = json.loads(raw_variations)
        except json.JSONDecodeError:
            variations = []

    variant = pick_canonical_variant(variations)
    price = int(variant["display_price"]) if variant and variant.get("display_price") is not None else None
    weight_g = None
    if variant:
        gm = GRAM_PATTERN.search(variant.get("attributes", {}).get("attribute_pa_gram", ""))
        if gm:
            weight_g = int(gm.group(1))

    all_out_of_stock = bool(variations) and not any(v.get("is_in_stock") for v in variations)
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
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(item["product_url"])
            detail = build_record(soup, item["product_url"], item["raw_name"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url, "")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_itsuki.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_itsuki.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
