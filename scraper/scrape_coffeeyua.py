# -*- coding: utf-8 -*-
"""
scrape_coffeeyua.py

○珈琲 Yu-A(ゆーあ)(www.coffeeyu-a.net、岐阜県岐阜市柳津町丸野2-97、
自家焙煎豆のオンライン販売)の商品情報を取得する。MakeShop。

コーポレートブログ(coffeeyu-a.com、WordPress、アフィリエイト広告
主体でショップ機能なし)とは別に、通販サイトがcoffeeyu-a.net
(www.coffeeyu-a.netへ301リダイレクト)に存在することを実データで
確認済み。特定商取引法相当の情報はhpgen/HPB/shop/business.htmlに
「所在地：〒501-6115　岐阜市柳津町丸野2-97」と明記されている。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、
Disallow指定は無く実質許可。

【商品一覧の取得方法について】
実データ確認済み: 商品カテゴリ「珈琲豆200g」(586203、ブレンド/ストレート/
デカフェの3小カテゴリ)・「珈琲豆Mail便(送料込)」(861087、同じく3小
カテゴリ)・「珈琲豆500g」(922091)の親ページ・小カテゴリページ計9ページを
巡回し、商品コード(a-XXXX/i-XXXX/j-XXXX形式)へのリンクを和集合で収集
する。親カテゴリページと小カテゴリページとで実際に掲載される商品コードの
集合が一致しない(親ページにしか出てこないコードがある)ことを確認済み
のため、両方を巡回する必要がある。「珈琲生豆」(638160、焙煎前の生豆で
自家焙煎豆ではない)・「珈琲器具」(645248)・「珈琲Gift」(687694)・
「珈琲の好敵手」(644981、黒糖ココア)・「珈琲の相棒」(752818、空)は
対象外としCATEGORY_PATHSに含めない。

【Mail便(送料込)版との重複について】
実データ確認済み: 同一銘柄が「通常版」(カテゴリ586203、送料別)と
「Mail便版」(カテゴリ861087、送料込みのため通常版より価格が高い)の
2商品として別々の商品コードで登録されている(例: a-0001「Yu-Aブレンド
200g/1180円」とi-0001「珈琲豆Mail便(送料込) Yu-Aブレンド200g/1380円」は
同一銘柄)。<title>タグの3番目のセグメント(「銘柄名+重量/価格円」が
区切り無しで連結された文字列)から「Mail便(送料込/送料無料)」の接頭辞と
重量・価格を取り除いた残りを基準名としてグルーピングし、価格の安い方
(=通常版)を代表として採用する。稀に通常版が欠品中でMail便版しか存在
しない銘柄(例: インドネシアマンデリン)もあるため、その場合はMail便版を
単独採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「珈琲豆500g」カテゴリのj-0003は特定の銘柄名を持たない
汎用「珈琲豆500g」商品(タイトルに価格の記載が無く、備考欄で銘柄を
選ぶ形式と推測される)で、単一銘柄と特定できないため除外する。
<title>から価格(/NNN円)を抽出できない商品は同様に除外する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "○珈琲 Yu-A",
    "url": "https://www.coffeeyu-a.net/",
    "platform": "MakeShop",
    "address": "岐阜県岐阜市柳津町丸野2-97",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため"
                          "Disallow指定は無い)",
}

BASE_URL = "https://www.coffeeyu-a.net"
CATEGORY_PATHS = [
    "SHOP/586203/list.html", "SHOP/586203/667684/list.html",
    "SHOP/586203/667698/list.html", "SHOP/586203/1172742/list.html",
    "SHOP/861087/list.html", "SHOP/861087/1153589/list.html",
    "SHOP/861087/1153590/list.html", "SHOP/861087/1172748/list.html",
    "SHOP/922091/list.html",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

MAIL_PREFIX_PATTERN = re.compile(r"^(?:珈琲豆|珈琲)?Mail便\([^)]*\)\s*")
PRICE_SUFFIX_PATTERN = re.compile(r"/\s*(\d+)円\s*$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    codes: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select('a[href^="/SHOP/"]'):
            m = re.match(r"^/SHOP/([a-zA-Z0-9-]+)\.html$", a.get("href", ""))
            if m:
                codes.add(m.group(1))
    return [f"{BASE_URL}/SHOP/{code}.html" for code in codes]


def extract_fields(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.find("title")
    if not title_el:
        return None
    segments = title_el.get_text().split("｜")
    if len(segments) < 3:
        return None
    segment = segments[2].strip()

    price_m = PRICE_SUFFIX_PATTERN.search(segment)
    if not price_m:
        # 銘柄名+価格の形式に一致しない(例: 汎用「珈琲豆500g」)ため対象外
        return None
    price = int(price_m.group(1))

    name_and_weight = segment[:price_m.start()].strip()
    name_and_weight = MAIL_PREFIX_PATTERN.sub("", name_and_weight).strip()
    weight_m = WEIGHT_PATTERN.search(name_and_weight)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base_name = WEIGHT_PATTERN.sub("", name_and_weight).strip()
    if not base_name:
        return None

    return {"title": base_name, "price": price, "weight_g": weight_g, "url": product_url}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        existing = by_base_name.get(item["title"])
        if existing is None or (item["price"] or float("inf")) < (existing["price"] or float("inf")):
            by_base_name[item["title"]] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
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
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if fields:
            all_items.append(fields)

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
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
    with open("data_coffeeyua.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeyua.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
