# -*- coding: utf-8 -*-
"""
scrape_sachine.py

幸音珈琲(sachinecoffee.com、埼玉県朝霞市)の商品情報を取得する。Denim bis
(scrape_denimbis.py)と同じOcnk(おちゃのこネット)プラットフォームだが、
テーマのバージョンが異なる(実データ確認済み、2026-09時点。Denim bisは
a.item_data_link/div.item_data[data-product-id]のクラス構成、本店は
touch024テーマでa.list_item_link/div.list_item_dataという別クラス構成。
div.page_box.itemlistというカテゴリ本体のコンテナ自体は共通)。

robots.txt確認済み(2026-09時点): GPTBot・Bytespider・TikTokSpider・
meta-externalagentのAI学習系クローラーのみ個別にDisallow: /指定があるが、
User-agent: *ルールには記述が無く実質全面許可(識別可能なUser-Agentを使用)。

【対象カテゴリについて】
「ブレンドコーヒー」(product-list/1、3件)・「ストレートコーヒー」
(product-list/2、6件)を対象とする(計9件、いずれもページネーション無し、
div.page_box.itemlist.without_pagerで終端を確認済み)。「ドリップバッグ
コーヒー」(3)・「アイスコーヒー」(5)・「業務用コーヒー」(9)・「ギフト
セット」(6)は対象外。

【商品詳細ページを個別に取得しない理由】
実データ確認済み: 商品詳細ページの説明文(div.item_desc_text)には産地・精選
方法・品種等のラベル付き構造化データが一切無く、マーケティング文のみ
(Denim bisの《産地構成》記法のようなブレンド内訳表記も無い)。一覧ページの
情報(商品名・価格帯)だけで完結させ、産地・精選方法・グレード等はすべて
商品名からcoffee_parser.parse_product()で判定する(例:「モカ　イルガチェフ」
→地域名逆引きでエチオピア、「マンデリン ジェームス オンド リントン」→
特定銘柄判定でインドネシア)。

【在庫状態について】
実データ確認済み: 一覧・詳細ページのいずれにも品切れ・終売を示す構造化要素が
見当たらない(Denim bisと同じ状況)。商品名のテキストマーカーのみで判定する
(coffee_parser.detect_stock_status)。

【価格が全商品同一の価格帯表記である点について】
実データ確認済み: 全9件が例外なく「750円～7,200円」という同一の価格帯表記
(内容量の異なる複数バリエーションによる価格幅とみられる)。店舗側の一律
設定であり誤取得ではないことを確認済みのため、price_min/price_maxへ
そのまま採用する。
"""

import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "幸音珈琲",
    "url": "https://www.sachinecoffee.com/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "埼玉県朝霞市本町1-10-30",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot・Bytespider・TikTokSpider・meta-externalagentの"
                          "AI学習系クローラーのみ個別にDisallow: /指定があるが、User-agent: *には"
                          "記述が無い。本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.sachinecoffee.com"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(コーヒー豆単品の2カテゴリのみ対象)
LIST_CATEGORIES = {
    "1": "ブレンドコーヒー",
    "2": "ストレートコーヒー",
}

PRICE_PATTERN = re.compile(r"([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list(cid: str, category_hint: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/product-list/{cid}")
    container = soup.select_one("div.page_box.itemlist")
    items = container.select("li.list_item_cell") if container else []

    results = []
    for item in items:
        link_el = item.select_one('a[href*="/product/"]')
        name_el = item.select_one("span.goods_name")
        if not link_el or not name_el:
            continue

        raw_name = name_el.get_text(strip=True)
        product_url = link_el.get("href", "")

        price_min, price_max = None, None
        figure_el = item.select_one("span.figure")
        if figure_el:
            numbers = PRICE_PATTERN.findall(figure_el.get_text())
            if numbers:
                price_min = int(numbers[0].replace(",", ""))
                price_max = int(numbers[-1].replace(",", ""))

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price_min": price_min,
            "price_max": price_max,
            "category_hint": category_hint,
        })
    return results


def build_record(item: dict) -> dict:
    raw_name = item["raw_name"]
    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price_min": item.get("price_min"),
            "price_max": item.get("price_max"),
            "product_url": item.get("product_url"),
        }

    parsed = apply_category_hint_fallback(parsed, item.get("category_hint"))
    stock_status = detect_stock_status(raw_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "category_hint": item.get("category_hint"),
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price_min": item.get("price_min"),
        "price_max": item.get("price_max"),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item.get("product_url"),
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid, category_hint):
            items_by_url.setdefault(item["product_url"], item)
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price_min=item.get("price_min"),
            price_max=item.get("price_max"),
        ):
            records.append(prev)
            continue

        detail = build_record(item)
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_sachine.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_sachine.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
