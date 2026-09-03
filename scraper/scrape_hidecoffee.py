# -*- coding: utf-8 -*-
"""
scrape_hidecoffee.py

HIDE COFFEE BEANS STORE(hidecoffee.com、東京都江東区東雲・豊洲)の商品情報を
取得する。実店舗サイト(www.hidecoffee.com)自体はWordPressの情報サイトで、
実際のオンラインショップは別ドメイン(shop.hidecoffee.com、バックエンドは
hidecoffee.shop-pro.jp、カラーミーショップ)で行われている「情報サイトと
通販サイトが別ドメイン」パターン(たまじ珈琲等と同様)。

robots.txt確認済み(2026-09時点): www.hidecoffee.com側はWordPress標準
(/wpcms/wp-admin/のみDisallow、YOAST SEOブロックでUser-agent: *は無制限)。
実際にスクレイピングするshop.hidecoffee.com側も同一のCAFE FACON等と同じ
カラーミー標準の記述(/secure/・/cart/のみ制限、確認済み)。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆「ブレンド」」(2888981、3件)・「コーヒー豆
「シングルオリジン」」(2889177、11件)・「カフェインレス」(2889178、1件)の
3カテゴリがコーヒー豆単品を指す。「コーヒーバッグ」(2889179)・
「ギフトセット」(2889180)・「器具類」(2889181)・「オリジナル商品」
(2889182)・「ラテベース」(2889183)は対象外。全商品の商品名に焙煎度合い
(シティロースト/フレンチロースト等)と重量(200g)が明記されている。

【在庫について】
inventory_controlが"none"、stock_numは常にnull(kunikuni.py・麻布珈房と
同じ運用)。商品名のテキストのみで在庫状態を判定する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "HIDE COFFEE BEANS STORE",
    "url": "https://shop.hidecoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都江東区東雲1-2-1",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみ制限。"
                          "nericafe・麻布珈房等と同一の記述)",
}

BASE_URL = "https://shop.hidecoffee.com"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "2888981": "ブレンド",
    "2889177": "シングルオリジン",
    "2889178": "カフェインレス",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def build_record(product_url: str, colorme_product: dict, category_hint: str) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)
    price = colorme_product.get("sales_price_including_tax")

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

    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": (lambda m: int(m.group(1)) if m else None)(WEIGHT_PATTERN.search(title)),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, colorme_product, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    results = []
    for h2 in soup.select("h2.title-ex-small"):
        link_el = h2.select_one('a[href*="pid="]')
        if not link_el:
            continue
        href = link_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        title = link_el.get_text(strip=True)
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            elif not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_hidecoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_hidecoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
