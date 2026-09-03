# -*- coding: utf-8 -*-
"""
scrape_toriba.py

TORIBA COFFEE(東京都中央区八重洲、旧・銀座本店)の商品情報を取得する。実店舗
サイト(www.toriba-coffee.com)自体は店舗案内中心で、実際のオンラインショップは
別ドメイン(www.toribacoffee-online.com、MakeShop)で行われている「情報
サイトと通販サイトが別ドメイン」パターン(たまじ珈琲等と同様)。神楽坂珈琲
焙煎所と同じMakeShopだが、テーマ・URL形式が異なる(/view/category/ctN・
/view/item/N ではなく /shopbrand/ctN・/shopdetail/N)。

【住所について】
実データ確認済み(2026-09時点): ユーザー指定の「銀座本店」(旧住所:東京都
中央区銀座7-8-13)は2022年秋に一度閉店しており、2023年にYANMAR TOKYO内
(東京都中央区八重洲2-1-1 B1F)で営業再開したことをGoogleマップ・PR TIMES
記事で確認済み。現在の住所を採用する。

robots.txt確認済み(2026-09時点): www.toribacoffee-online.com側はrobots.txt
自体が存在せず404(EUC-JPの汎用404ページ。神楽坂珈琲焙煎所・CAFE FACON等と
同種の「robots.txtが無い=実質全面許可」状態)。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆」(ct2、35件)がコーヒー豆単品の全件を指す。
「コーヒー豆,LIQUID／リキッド」(ct24、2件)はct2に完全に含まれる重複ビュー
であることをID突き合わせで確認済み。「ギフトセット・包装」(ct3)・「コーヒー
器具」(ct4)は対象外。

【「コーヒー豆」カテゴリ内の非コーヒー豆除外について】
実データ確認済み: ct2内に「ドリップパック」単品/セット商品、「ROASTED
BANCHA 煎り番茶」(コーヒーではなく緑茶の焙じ茶)、「COFEE CHAI」「SPICE
COFFEE」(スパイスミックス)、「ミルクコーヒーベース」「リキッドアイス
コーヒー」(既製飲料)、「コーヒー定期便」(サブスクリプション)が混在している
ため、NON_BEAN_KEYWORDSで除外する。

【商品説明・在庫について】
実データ確認済み: 商品詳細ページの説明文はHTMLコメント内に格納されており
(隠房の住所欄と同種の状況)、安定して取得できないため商品名解析のみに頼る。
在庫切れを示す構造化要素も見当たらないため、商品名のテキストのみで在庫状態を
判定する。価格はinput#M_price2のvalue属性(税込)から取得する(JSで生成される
JSON-LDはブラウザでのみ生成され静的HTMLには含まれないため使わない)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "TORIBA COFFEE",
    "url": "https://www.toribacoffee-online.com/",
    "platform": "MakeShop",
    "address": "東京都中央区八重洲2-1-1 YANMAR TOKYO B1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。robots.txtが存在せず404。"
                          "神楽坂珈琲焙煎所・CAFE FACON等と同種の"
                          "「実質全面許可」状態)",
}

BASE_URL = "https://www.toribacoffee-online.com"
CATEGORY_ID = "ct2"  # コーヒー豆。理由はモジュールdocstring参照
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップパック", "BANCHA", "番茶", "CHAI", "SPICE COFFEE",
    "ミルクコーヒーベース", "リキッド", "コーヒー定期便",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def build_record(product_url: str, title: str, price: int | None) -> dict:
    parsed = parse_product(title)

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
        "price": price,
        "weight_g": (lambda m: int(m.group(1)) if m else None)(WEIGHT_PATTERN.search(title)),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, fallback_title: str = "") -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("p.itemName, h1")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": url,
        }

    price = None
    price_el = soup.select_one("#M_price2")
    if price_el and price_el.get("value"):
        price = int(price_el["value"].replace(",", ""))

    return build_record(url, title, price)


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/shopbrand/{CATEGORY_ID}")
    results = []
    for item in soup.select("li.itemList__unit"):
        link_el = item.select_one('a[href*="/shopdetail/"]')
        title_el = item.select_one("p.itemName")
        if not link_el or not title_el:
            continue
        title = title_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"], item["raw_name"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_toriba.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_toriba.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
