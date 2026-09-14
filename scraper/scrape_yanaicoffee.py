# -*- coding: utf-8 -*-
"""
scrape_yanaicoffee.py

自家焙煎ヤナイコーヒー商会(yanai-coffee.net、〒970-8031 福島県いわき市平中山字
矢ノ倉33-108、自家焙煎豆のオンライン販売。本店+「Sons」小名浜支店の2拠点)の
商品情報を取得する。WordPress(WooCommerce)。

【住所について】
公式サイトの「当店の紹介」ページ(https://yanai-coffee.net/?page_id=61)で実データ
確認(2026-09時点): 本店〒970-8031 福島県いわき市平中山字矢ノ倉33-108、
小名浜支店(Sons)〒971-8101 福島県いわき市小名浜定西57-1。オンライン通販は本店の
1つのショップとして運営されており、商品ごとに取扱店舗が分かれている実データは
確認できなかったため、本スクレイパーでは本店住所を代表として採用する(複数拠点
だが商品が店舗別に分かれていないためlocationsパターンは使わない)。

robots.txt確認済み(2026-09時点): https://yanai-coffee.net/robots.txtは404
Not Foundが返る(実質存在しない)。クロール制限の記述が無いため実質無制限と
判断した(1518coffee.py等と同一の状況)。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点): 「豆の種類と購入」ページ(?page_id=59)に全19件の
`?product=商品名`形式のリンクが並ぶ。ページネーション無し。

【除外商品について】
実データ確認済み: 「キャラメルフレーバードリップバッグ６個入」「いわき味巡り
ドリップバッグ」「メキシコディカフェ【ドリップバッグ】」「水出しコーヒーバッグ
【hotcold】」の4件がドリップバッグ・水出しバッグ形式で、焙煎豆単品ではないため
キーワード除外する。「メキシコディカフェ」はドリップバッグ版とは別に
「ブラジルデカフェ（100g）」という通常の焙煎豆デカフェ商品も別途存在する。

【商品詳細ページのJSON-LD構造化データについて】
実データ確認済み: WooCommerce標準のJSON-LD(schema.org Product)が商品ページに
埋め込まれており、name/offers.priceSpecification.price/offers.availabilityを
安定して取得できる。商品名には<br>タグが含まれることがある(例:「　ガテマラ<br>
　（100g）」)ため、タグを空白に置換してから整形する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎ヤナイコーヒー商会",
    "url": "https://yanai-coffee.net/",
    "platform": "WordPress(WooCommerce)",
    "address": "福島県いわき市平中山字矢ノ倉33-108",
    "prefecture": "福島県",
    "robots_txt_status": "実質無制限(2026-09確認。robots.txtは404 Not Foundが返り、"
                          "実質的な制限記述が無い)",
}

BASE_URL = "https://yanai-coffee.net"
PRODUCT_LIST_URL = f"{BASE_URL}/?page_id=59"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照(ドリップバッグ・水出しバッグ形式は焙煎豆単品でない)
NON_BEAN_KEYWORDS = ["ドリップバッグ", "水出しコーヒーバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
JSONLD_PATTERN = re.compile(r'<script type="application/ld\+json">(\{.*?"@type":"Product".*?\})</script>', re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(PRODUCT_LIST_URL)
    urls = []
    seen = set()
    for a in soup.select('a[href*="?product="]'):
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
    return urls


def extract_jsonld_product(html: str) -> dict | None:
    m = JSONLD_PATTERN.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def clean_title(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", raw)
    text = text.replace("　", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_record(product_url: str) -> dict | None:
    resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    data = extract_jsonld_product(resp.text)
    if not data:
        return None

    title = clean_title(data.get("name") or "")
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {"shop_name": SHOP_INFO["name"], "raw_name": title, "non_bean": True, "product_url": product_url}

    parsed = parse_product(title)
    # 実データ確認済み(2026-09時点): 「温泉さんぽぶれんど」等、ブレンド商品名が
    # 平仮名の「ぶれんど」表記(coffee_parser.BLEND_KEYWORDSはカタカナ「ブレンド」/
    # 英語"blend"のみに対応)のため、商品名からの分類のみでは検出できない。
    # このスクレイパー内でのみ平仮名表記を補って分類を補正する
    # (coffee_parser.py自体は全店舗共通のため変更しない)。
    if "ぶれんど" in title and parsed["category"] != "ブレンド":
        parsed["category"] = "ブレンド"
    weight_m = WEIGHT_PATTERN.search(title)

    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    offers = offers or {}
    price_spec = offers.get("priceSpecification")
    if isinstance(price_spec, list):
        price_spec = price_spec[0] if price_spec else {}
    price = None
    if price_spec and price_spec.get("price"):
        price = int(float(price_spec["price"]))
    elif offers.get("price"):
        price = int(float(offers["price"]))

    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url in product_urls:
        try:
            detail = build_record(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_yanaicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yanaicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
