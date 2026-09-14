# -*- coding: utf-8 -*-
"""
scrape_catracha.py

カトラッチャ珈琲焙煎所(catracha-cb.shop-pro.jp、愛媛県伊予市双海町串
3561-2、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミー
ショップ(shop-pro.jp)。

【住所について】
実データ確認済み(2026-09時点): 候補リストでは「愛媛県大洲市五郎2682」
(Yahoo!ロコ・食べログ等の第三者情報源に基づく実店舗所在地)とされていた
が、公式ストア(catracha-cb.shop-pro.jp)自身の特定商取引法ページ
(https://catracha-cb.shop-pro.jp/?mode=sk)を実データ確認したところ
「〒799-3312 愛媛県伊予市双海町串3561-2」と記載されている。実店舗(大洲市
五郎、河川敷での焙煎・テイクアウト営業)と通信販売の事業者登録上の所在地
(伊予市双海町、自宅等の可能性)が異なるケースと考えられるが、本プロジェクト
の一次情報優先の方針(第三者情報源より公式tokushoho記載を優先)に基づき、
特定商取引法ページの住所を採用する。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ
Disallow。AhrefsBot等一部ボットは個別にDisallow: /、それ以外は制限なし。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=euc-jp)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み: 全50件中「コーヒー豆」カテゴリ(cbid=2527340)が
ストレート/フレーバー系のコーヒー豆単品を含む。他カテゴリ(カフェ・
ドリップコーヒー・グッズ・その他)は非対象と判断し、NON_BEAN_KEYWORDSと
category_hintの両方で除外する。

【重量・在庫について】
実データ確認済み: inventory_control="none"(在庫管理なし、他のColorme
店舗と同じ)のため、商品名のテキストのみからdetect_stock_status()で
判定する。商品名に重量表記(200g等)が含まれる。バリアントは挽き方
(豆のまま/挽き豆)のみで価格は同一のため、sales_price_including_taxを
そのまま使う。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "カトラッチャ珈琲焙煎所",
    "url": "https://catracha-cb.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "愛媛県伊予市双海町串3561-2",
    "prefecture": "愛媛県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *は/secure/・/cart/のみ"
                          "Disallow。AhrefsBot等一部ボットは個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://catracha-cb.shop-pro.jp"
# 理由はモジュールdocstring参照(コーヒー豆カテゴリのみが対象)
BEAN_CATEGORY_ID = "2527340"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップ", "ワッフル", "スイーツ", "グッズ", "ギフト", "ボックス", "アイス",
    "カフェバッグ", "水出し",
]
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=euc-jp)
    return BeautifulSoup(resp.text, "html.parser")


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def scrape_category_list(cid: str) -> list[str]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    urls = []
    for link in soup.select('a[href*="pid="]'):
        href = link.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        if product_url not in urls:
            urls.append(product_url)
    return urls


def build_record(product_url: str, colorme_product: dict) -> dict | None:
    # 理由: 一部商品名にバックスペース等の制御文字が混入していることを実データ
    # 確認済み(例: 「ナンシーさんのコーヒー\x08【ナチュラル】【中煎】200g」)。
    # parse_product()や表示に影響するため除去する。
    title = CONTROL_CHAR_PATTERN.sub("", (colorme_product.get("name") or "")).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return None
    return build_record(url, colorme_product)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = scrape_category_list(BEAN_CATEGORY_ID)

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_catracha.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_catracha.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
