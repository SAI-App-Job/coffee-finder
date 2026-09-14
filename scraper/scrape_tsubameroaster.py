# -*- coding: utf-8 -*-
"""
scrape_tsubameroaster.py

自家焙煎 燕珈琲(つばめコーヒー、tsubameroaster.jp、鳥取県鳥取市用瀬町宮原
38-6、自家焙煎豆のオンライン販売)の商品情報を取得する。

【プラットフォームについて】
実データ確認済み: BASE/カラーミー/Shopify/STORESのいずれでもない独自
プラットフォーム。JSやCSSが"xaas3.jp"というドメインから読み込まれており、
Web検索の結果、これは株式会社アイフラッグが提供する「ホームページマイスター
for ネットショップ」というASP型ECサービスと判明した。本プロジェクトで初めて
対応するプラットフォームのため、汎用のBeautifulSoupベースの実装とする
(このプラットフォームは同一店舗名で運営される鳥取県下関市のウミノネ
コーヒー(scrape_uminonecoffee.py)でも使われている)。

robots.txt確認済み(2026-09時点): User-agent: *に対し/default/error/・
/preview/のみDisallow。それ以外は制限なし。Crawl-delayの指定は無い。

【商品カテゴリの構成について】
実データ確認済み(2026-09時点): カテゴリはCategory 1(Coffee、豆売り
13件)・Category 2(Craft Chocolate、チョコレート)・Category 3(Gift、
ギフトセット)・Category 5(雑貨、バッグ・革小物等)の4つ。コーヒー豆
商品はCategory 1にのみ存在するため、このカテゴリのみをクロール対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み(Category 1、全13件): 水出し珈琲(20gx4、ティーバッグ状の
水出し専用パック)・カフェインレスカフェオレベース(無糖、リキッド)・
ドリップバッグ5つセット・カフェオレベース(無糖、リキッド)の4件が非対象。
NON_BEAN_KEYWORDSで除外する。残り9件(ストレート8種＋TSUBAME BLEND、
いずれも200g)を対象とする。

【商品一覧のHTML構造について】
実データ確認済み: カテゴリページ(/category/<ID>)のul.itemList > liの中に
p.name>a(商品名・URL)、p.price(「販売価格:X円（税込）」形式、複数ある
場合は最初が通常価格)、number欄の在庫切れ画像(alt="在庫切れボタン")が
構造化されている。ページネーションはCategory 1の場合1ページ(全13件)で
収まるため追加対応は行わない。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎 燕珈琲",
    "url": "https://www.tsubameroaster.jp/",
    "platform": "ホームページマイスター for ネットショップ(株式会社アイフラッグ、独自ASP)",
    "address": "鳥取県鳥取市用瀬町宮原38-6",
    "prefecture": "鳥取県",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/・/preview/のみ"
                          "Disallow、それ以外は制限なし。Crawl-delayの指定なし)",
}

BASE_URL = "https://www.tsubameroaster.jp"
COFFEE_CATEGORY_URL = f"{BASE_URL}/category/1"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "水出し", "カフェ・オ・レ・ベース", "カフェオレベース", "ドリップバッグ",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"販売価格[：:]\s*([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(COFFEE_CATEGORY_URL)
    results = []
    for li in soup.select("ul.itemList > li"):
        name_el = li.select_one("p.name > a")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        price_el = li.select_one("p.price")
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        out_of_stock_img = li.select_one('img[alt*="在庫切れ"]')

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "structural_out_of_stock": out_of_stock_img is not None,
        })
    return results


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_item_list()

    records = []
    flavored_records = []
    for item in items:
        detail = build_record(item)
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
    with open("data_tsubameroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tsubameroaster.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
