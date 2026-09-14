# -*- coding: utf-8 -*-
"""
scrape_ripplecoffee.py

ripple coffee(nowavecoffee.stores.jp、香川県高松市塩上町1-7-5、深煎り
自家焙煎豆のオンライン販売)の商品情報を取得する。STORES。

【住所について】
実データ確認済み(2026-09時点): 公式ストアの/tokushohoページ
(https://nowavecoffee.stores.jp/tokushoho)には「※所在地・電話番号には、
STORES を運営する STORES 株式会社 の情報が表示されています」との注記があり、
記載の住所(東京都渋谷区)はSTORES社自身のプロキシ住所であって本ショップの
住所ではない。一方、本ショップ自身のABOUTページ(一次情報、
https://nowavecoffee.stores.jp/about)には「ripplecoffee 自家焙煎珈琲豆の
販売店 香川県高松市塩上町1-7-5 深煎り珈琲豆専門店」と明記されており、
候補リストの住所と一致確認済み。ABOUTページはショップ自身が編集する一次
情報であり、tokushohoのプロキシ表示より信頼できるためこれを採用する。

robots_txt確認済み(2026-09時点): 他のSTORES系店舗と同一の記述
(Crawl-delay: 20。/items/は対象外。/tokushohoはDisallow対象だが本スクレイパー
はABOUTページを利用するため影響なし)。本スクレイパーはrobots.txtの
Crawl-delay: 20に従い、リクエスト間に20秒の間隔を設ける。

【Cloudflare対策について】
理由は他のSTORES系スクレイパーと同様(scrape_mikazukido.py等参照)。一般的な
ブラウザ相当のUser-Agent/Accept-Languageヘッダーを付けて再試行する。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全9件): 「ripple coffee neldriper」(ネルドリッパー
器具)・「ドリップパック アソート」(ドリップバッグ)・「卸」(名称のみで産地
情報が無い卸売専用のSOLD OUT表示商品、直営店ABOUTページの「卸売」記載に
対応する内部的なSKUと判断)が非対象。残り6件(ブレンド2種+ストレート4種、
いずれも200g規格)が対象。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ripple coffee",
    "url": "https://nowavecoffee.stores.jp/",
    "platform": "STORES",
    "address": "香川県高松市塩上町1-7-5",
    "prefecture": "香川県",
    "robots_txt_status": "許可(2026-09確認。他のSTORES系店舗と同一の記述。"
                          "Crawl-delay: 20が明示されている。/items/は対象外)",
}

BASE_URL = "https://nowavecoffee.stores.jp"
CRAWL_DELAY_SECONDS = 20  # robots.txtのCrawl-delay: 20に従う
NON_BEAN_KEYWORDS = ["neldriper", "ドリップパック", "アソート", "卸"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) CoffeeFinderBot/0.1 Chrome/124.0.0.0 Safari/537.36 "
                  "(+contact: your-contact-info-here)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)


def fetch_page(url: str, retries: int = 2) -> BeautifulSoup:
    last_exc = None
    for attempt in range(retries + 1):
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 403 and attempt < retries:
            # 理由はモジュールdocstring参照(Cloudflareの一時的なチャレンジ)
            time.sleep(3)
            continue
        try:
            resp.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            continue
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    raise last_exc or requests.RequestException(f"failed to fetch {url}")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/items")
    results = []
    for link_el in soup.select("a.c-itemList__item-link[href]"):
        name_el = link_el.select_one(".c-itemList__item-name")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        sold_out = link_el.select_one(".c-itemList__item-sold") is not None
        results.append({"raw_name": raw_name, "product_url": product_url, "sold_out": sold_out})
    return results


def build_record(product_url: str, raw_title: str, price: int | None, sold_out: bool) -> dict | None:
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(raw_title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(raw_title, sold_out)
    weight_m = WEIGHT_PATTERN.search(raw_title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_title,
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


def parse_product_detail(url: str, sold_out: bool) -> dict | None:
    soup = fetch_page(url)
    html = str(soup)

    title_el = soup.select_one("h1.item_name")
    raw_title = title_el.get_text(strip=True) if title_el else ""
    if not raw_title:
        return None

    price_match = re.search(r"detailCtrl\.salesPrice\s*=\s*(\d+)", html)
    price = int(price_match.group(1)) if price_match else None

    return build_record(url, raw_title, price, sold_out)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    list_items = scrape_item_list()
    time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    flavored_records = []

    for item in list_items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            detail = parse_product_detail(item["product_url"], item["sold_out"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        finally:
            time.sleep(CRAWL_DELAY_SECONDS)
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
    with open("data_ripplecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ripplecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
