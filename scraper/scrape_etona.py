# -*- coding: utf-8 -*-
"""
scrape_etona.py

エトナコーヒー(www.etonacoffee.com、千葉県千葉市花見川区幕張)の商品
情報を取得する。MakeShop(GMOメイクショップ)。このプロジェクト初の
EUC-JPエンコードのMakeShop店舗(神楽坂珈琲焙煎所はUTF-8)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみ個別にDisallow: /、それ以外(本スクレイパーの
User-Agentを含む)は制限なし。

【エンコーディングについて】
実データ確認済み: レスポンスヘッダ・HTML双方でcharset=EUC-JPと明記
されている。requestsは自動でEUC-JPを認識するため明示的な
resp.encoding指定は不要(コーヒーランドのUTF-8バグとは異なり、
サーバー側がcharsetを正しく宣言しているケース)。

【カテゴリ構造について】
実データ確認済み: 左メニューのカテゴリは「すべての商品」「セット＆ギフト
(sample1)」「ブレンドcoffee(sample2, 30件)」「ストレートcoffee(sample3,
231件、1ページ50件×5ページ)」「ドリップバッグ(ct12)」「teaリスト(ct5)」
「フィルター・雑貨(ct13)」。コーヒー豆単品はsample2+sample3の2カテゴリに
限定されており(実データ確認済み、セット/ギフト/器具系キーワードは
sample2・sample3内に一切出現しない)、この2カテゴリの一覧ページのみを
対象とする。

【重量違いの重複について】
実データ確認済み: 同一銘柄が「イルガG1　200ｇ」「イルガG1　500ｇ」
「イルガG1　1kg」のように重量ごとに完全に独立した商品ページ(別々の
shopdetail ID)として登録されている(Shopifyのバリアント方式とは異なる)。
そのため商品名末尾の重量表記を取り除いた基準名でグルーピングし、
最小重量の商品を代表として採用する(全350件中、対象カテゴリの重複排除後は
88銘柄)。

【価格(税込換算)について】
実データ確認済み: 一覧ページに表示される価格は税抜表示(例:「6,000円
（税抜）」)のみ。個別の商品詳細ページのOGPタグ(product:price:amount)で
複数商品の税込価格を実地検証したところ、いずれも税抜価格×1.08(食品の
軽減税率8%)を四捨五入した値と一致した(例: 6,000円→6,480円、
4,500円→4,860円、1,120円→1,210円)。231件全件の詳細ページを個別取得する
コストを避けるため、一覧ページの税抜価格に対しこの換算式を適用して
税込価格を算出する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "エトナコーヒー",
    "url": "https://www.etonacoffee.com/",
    "platform": "MakeShop",
    "address": "千葉県千葉市花見川区幕張",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.etonacoffee.com"
LIST_PAGES = [
    "/shopbrand/sample2/",
    "/shopbrand/sample3/",
    "/shopbrand/sample3/page2/recommend/",
    "/shopbrand/sample3/page3/recommend/",
    "/shopbrand/sample3/page4/recommend/",
    "/shopbrand/sample3/page5/recommend/",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|ｋｇ|g|ｇ)", re.IGNORECASE)
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*(?:kg|ｋｇ|g|ｇ)\s*$", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ITEM_ID_PATTERN = re.compile(r"/shopdetail/(\d+)/")
TAX_RATE = 1.08


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    return value * 1000 if unit in ("kg", "ｋｇ") else value


def canonical_url(href: str) -> str:
    m = ITEM_ID_PATTERN.search(href)
    item_id = m.group(1) if m else ""
    return f"{BASE_URL}/shopdetail/{item_id}/"


def scrape_list_page(path: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}{path}")
    items = []
    for box in soup.select("div.innerBox"):
        name_el = box.select_one("p.name a")
        price_el = box.select_one("p.price em.price")
        if not name_el or not price_el:
            continue
        title = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        price_match = PRICE_PATTERN.search(price_el.get_text())
        price_excl_tax = int(price_match.group(1).replace(",", "")) if price_match else None
        items.append({
            "raw_name": title,
            "product_url": canonical_url(href),
            "price_excl_tax": price_excl_tax,
            "weight_g": parse_weight_g(title),
        })
    return items


def pick_canonical_items(all_items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in all_items:
        base_name = TRAILING_WEIGHT_PATTERN.sub("", item["raw_name"]).strip()
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight = existing["weight_g"] if existing and existing["weight_g"] is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict:
    title = item["raw_name"]
    parsed = parse_product(title)

    price = None
    if item["price_excl_tax"] is not None:
        price = round(item["price_excl_tax"] * TAX_RATE)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": item["product_url"],
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
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: list[dict] = []
    for path in LIST_PAGES:
        all_items.extend(scrape_list_page(path))

    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        detail = build_record(item)
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
    with open("data_etona.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_etona.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
