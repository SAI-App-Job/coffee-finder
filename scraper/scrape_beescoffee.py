# -*- coding: utf-8 -*-
"""
scrape_beescoffee.py

ビーズコーヒー(BeesCoffee、東京都文京区千石)の商品情報を取得する。実店舗
サイト(www.beescoffee.com)自体には情報のみで、実際のオンラインショップは
別ドメイン(beescoffeeshop.shop-pro.jp、カラーミーショップ)で行われている
「情報サイトと通販サイトが別ドメイン」パターン(たまじ珈琲等と同様)。

robots.txt確認済み(2026-09時点): www.beescoffee.com自体はrobots.txt
リクエストが自ホームページへの302/301リダイレクトになる(=robots.txt自体が
存在しない、CAFE FACON・神楽坂珈琲焙煎所と同種の「実質全面許可」状態)。

【カテゴリ構造について】
実データ確認済み: トップページの4カテゴリ「コーヒー豆」(2393382、30件)・
「業務用」(2393383、30件、洗浄剤・グラインダー等の業務用機材)・「家庭用」
(2393384、30件、家庭用ドリッパー・ポット等)・「その他」(2393385、11件、
水出しパック・砂糖・味噌・カスカラシロップ等)は互いに重複の無い完全に
別々の商品群であることを確認済み(pidの重複ゼロ)。コーヒー豆単品を指すのは
「コーヒー豆」カテゴリのみで、他3カテゴリは全て非コーヒー豆のため対象外。

【「コーヒー豆」カテゴリ内の非コーヒー豆除外について】
実データ確認済み: 「コーヒー豆」カテゴリ(30件)にも、生豆(未焙煎)バリエーション
(既に焙煎豆版が別商品として存在する重複)・詰め合わせ商品・ドリップコーヒー
単品/セットが混在している。NON_BEAN_KEYWORDSで「生豆」「詰め合わせ」
「ドリップコーヒー単品」を除外する。

【在庫について】
inventory_controlが"none"、stock_numは常にnull(kunikuni.py・麻布珈房と
同じ運用)。商品名のテキストのみで在庫状態を判定する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ビーズコーヒー",
    "url": "https://beescoffeeshop.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都文京区千石1-29-15 LAアパートメント文京千石1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。robots.txtが存在せず"
                          "自ホームページへリダイレクトされる。CAFE FACON・"
                          "神楽坂珈琲焙煎所と同種の「実質全面許可」状態)",
}

BASE_URL = "https://beescoffeeshop.shop-pro.jp"
CATEGORY_ID = "2393382"  # コーヒー豆。理由はモジュールdocstring参照
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["生豆", "詰め合わせ", "ドリップコーヒー単品"]

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


def build_record(product_url: str, colorme_product: dict) -> dict:
    title = (colorme_product.get("name") or "").strip()

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

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


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, colorme_product)


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0")
    results = []
    for item in soup.select("li.prd_lst_unit"):
        title = None
        href = None
        for link in item.select('a[href*="pid="]'):
            text = link.get_text(strip=True)
            if text:
                title = text
                href = link.get("href", "")
                break
        if not title or not href:
            continue
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
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
            detail = parse_product_detail(item["product_url"])
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
        with open("data_beescoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_beescoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
