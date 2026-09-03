# -*- coding: utf-8 -*-
"""
scrape_mijinco.py

自家焙煎珈琲みじんこ(mijinco-coffee.net、東京都文京区湯島)の商品情報を
取得する。カラーミーショップ(shop-pro.jp)。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ制限
(nericafe・麻布珈房等と同一の記述)。

【対象カテゴリについて】
実データ確認済み: 「コーヒー」カテゴリ(cbid=2763945)配下に「コーヒー豆」
(csid=1)・「ドリップバッグ」(csid=2)・「リキッドコーヒー」(csid=3)の
3サブカテゴリがあり、csid=1「コーヒー豆」の3件のみが実際の豆単品(
＜No.1＞マイルドブレンド／＜No.2＞ビターブレンド／＜No.3＞フレッシュブレンド、
いずれも200g固定・全てブレンド)。「ホットケーキ」「プリン」「みじんこの
ギフト」「グッズ」等の他カテゴリは食品・雑貨のため対象外。かなり小規模な
カタログだが、実店舗・オンラインショップとも実在確認済み(2026-09時点)。

【商品名のbrタグについて】
実データ確認済み: var Colormeのproduct.nameに文字列としてそのまま
「＜No.1＞マイルドブレンド<br>(シティロースト 200g)」のようにHTMLタグの
<br>が埋め込まれている(実際のDOM要素ではなくJSON文字列内の生テキストのため、
BeautifulSoupのbrタグ変換は効かない)。半角スペースに置換してから
パースする。

【在庫について】
inventory_controlが"none"、stock_numは常にnull(kunikuni.py・麻布珈房と
同じ運用)。商品名のテキストのみで在庫状態を判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎珈琲みじんこ",
    "url": "http://www.mijinco-coffee.net/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都文京区湯島2-9-10 湯島三組ビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみ制限。"
                          "nericafe・麻布珈房等と同一の記述)",
}

BASE_URL = "http://www.mijinco-coffee.net"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2763945&csid=1"  # コーヒー豆。理由はモジュールdocstring参照
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


def build_record(product_url: str, colorme_product: dict) -> dict:
    raw_title = (colorme_product.get("name") or "").strip()
    title = re.sub(r"<br\s*/?>", " ", raw_title).strip()  # 理由はモジュールdocstring参照
    parsed = parse_product(title)

    price = colorme_product.get("sales_price_including_tax")
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


def scrape_category_list() -> list[dict]:
    soup = fetch_page(CATEGORY_URL)
    results = []
    for link_el in soup.select('a.itemWrap[href*="pid="]'):
        href = link_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        title_el = link_el.select_one("p.itemName")
        raw_title = title_el.decode_contents() if title_el else ""
        title = re.sub(r"<br\s*/?>", " ", raw_title).strip()
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> list[dict]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(item["product_url"])
            colorme_product = extract_colorme_product(soup)
            if colorme_product:
                records.append(build_record(item["product_url"], colorme_product))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records


if __name__ == "__main__":
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mijinco.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mijinco.json に出力しました")
