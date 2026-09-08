# -*- coding: utf-8 -*-
"""
scrape_nadacoffee.py

名田珈琲功房(nada-coffee.com、兵庫県加古川市加古川町美乃利246-2(焙煎工房・
事務所)、自家焙煎豆のオンライン販売)の商品情報を取得する。Welcart
(WordPress用ECプラグイン、プラグインスラッグ"usc-e-shop")。本プロジェクトで
初めてのWelcart店舗。

【プラットフォームについて】
実データ確認済み: ホームページのプラグイン読み込み(wp-content/plugins/
usc-e-shop, wp-content/plugins/snow-monkey-editor)およびカート/会員ページ
URL(/usces-cart/, /usces-member/)からWelcartであることを確認した。BASE/
カラーミー/Shopify/Ocnk/WooCommerce/EC-CUBEのいずれにも該当しない新規
プラットフォームだが、商品カテゴリ一覧ページ(/category/item/itemgenre/
item-item/)に商品名・価格が静的HTMLでそのまま出力されており(JS実行不要)、
商品詳細ページの`<span class="field_stock">在庫状態</span>`から在庫状況も
取得できるため、低リスクな抽出方法として実装する(自家焙煎珈琲キャビン珈琲=
ShopServeと同じ方針)。

robots.txt確認済み(2026-09時点): "Disallow: /wp/wp-admin/"のみ(admin-ajax.php
は明示的にAllow)。商品カテゴリページ・商品詳細ページへの制限記述なし。

【店名・住所について】
候補リストでは「名田珈琲功房 — Kakogawa、2 locations (main roastery +
directly-run café)」だったが、公式サイトの店舗情報ページ(https://
nada-coffee.com/information/)で確認したところ、焙煎工房・事務所の所在地は
「兵庫県加古川市加古川町美乃利246-2」であることを確認した。直営店「播磨
珈琲倶楽部」は別店舗として案内されているのみで住所詳細は店舗情報ページに
記載がないため、焙煎工房の住所を正としている。焙煎(自家焙煎)を行っている
ことも同ページで確認済み。

【商品一覧の取得方法について】
実データ確認済み: 商品カテゴリ「珈琲豆」(itemgenre/item-item、3ページ・
計25件)から取得する。姉妹カテゴリ「フード」(itemgenre/item-item-2、4件、
珈琲羊かんのみ)は最初から対象外のカテゴリを選ぶことで除外する。ページネー
ションは`.page-numbers`リンクから最大ページ番号を検出して巡回する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「珈琲豆」カテゴリ25件のうち「【珈琲関連商品】珈琲羊かん
200g」「【珈琲関連商品】珈琲羊かん 200g 化粧箱入り」「【珈琲関連商品】珈琲
羊かん（ビター） 200g」「【珈琲関連商品】珈琲羊かん（ビター） 200g 化粧箱
入り」(和菓子、コーヒー豆ではない)が非対象。NON_BEAN_KEYWORDSで除外する。
残り21件を対象とする。

【重量違いの重複について】
実データ確認済み: 「清流加古川ブレンド珈琲」「コク（ＫＯＭ）ブレンド珈琲」
「マイルドブレンド珈琲」「スペシャルブレンド珈琲」の4銘柄はそれぞれ
「２００ｇ」と「業務用５００ｇ」の2サイズが別商品として登録されている。
重量トークンを除いた基準名でグルーピングし、最小重量(200g)を代表として
採用する。なお「ブラジル単品焙煎珈琲」と「ブラジル単品焙煎珈琲【深煎り】」
(グァテマラも同様)は重量ではなく焙煎度の違いによる別商品名のため、
重複排除の対象にはならず両方とも別商品として残る。

【挽き方バリアントについて】
実データ確認済み: 商品詳細ページには「豆(ビーンズ)/極細挽/細挽/中細挽/
中挽/粗挽き」の挽き方セレクトボックスがあるが、価格は挽き方に依らず同一
(選択式オプションであり別商品ではない)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "名田珈琲功房",
    "url": "https://nada-coffee.com/",
    "platform": "Welcart",
    "address": "兵庫県加古川市加古川町美乃利246-2",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。Disallow: /wp/wp-admin/のみ、"
                          "商品カテゴリ・商品詳細ページへの制限記述なし)",
}

BASE_URL = "https://nada-coffee.com"
CATEGORY_URL = f"{BASE_URL}/category/item/itemgenre/item-item/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["珈琲関連商品", "羊かん"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"¥([\d,]+)")
ITEM_BLOCK_SPLIT = re.compile(r'__shopitem" id="num-')
PRODUCT_URL_PATTERN = re.compile(r'<a href="(https://nada-coffee\.com/\d{4}/\d{2}/\d{2}/[^"]+)"')
ALT_PATTERN = re.compile(r'alt="([^"]*)"')


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp


def discover_page_urls() -> list[str]:
    resp = fetch(CATEGORY_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    pages = {1: CATEGORY_URL}
    for a in soup.select("a.page-numbers"):
        href = a.get("href")
        text = a.get_text(strip=True)
        if href and text.isdigit():
            pages[int(text)] = href
    return [pages[n] for n in sorted(pages)]


def fetch_item_list() -> list[dict]:
    items: dict[str, dict] = {}
    for page_url in discover_page_urls():
        resp = fetch(page_url)
        for block in ITEM_BLOCK_SPLIT.split(resp.text)[1:]:
            url_m = PRODUCT_URL_PATTERN.search(block)
            alt_m = ALT_PATTERN.search(block)
            price_m = PRICE_PATTERN.search(block)
            if not url_m or not alt_m:
                continue
            product_url = url_m.group(1)
            if product_url in items:
                continue
            import html as ihtml
            title = ihtml.unescape(alt_m.group(1)).strip()
            price = int(price_m.group(1).replace(",", "")) if price_m else None
            if title:
                items[product_url] = {"title": title, "price": price, "url": product_url}
    return list(items.values())


def normalize_base_name(title: str) -> str:
    base = WEIGHT_PATTERN.sub("", title)
    return re.sub(r"\s+", " ", base).strip()


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for item in items:
        weight_matches = WEIGHT_PATTERN.findall(item["title"])
        weight_key = int(weight_matches[-1]) if weight_matches else float("inf")
        base = normalize_base_name(item["title"])
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def fetch_stock_status_text(product_url: str) -> str | None:
    try:
        resp = fetch(product_url)
    except requests.RequestException:
        return None
    m = re.search(r'class="field_stock">([^<]*)</span>', resp.text)
    return m.group(1) if m else None


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

    stock_text = fetch_stock_status_text(item["url"])
    structural_out_of_stock = bool(stock_text) and "在庫有り" not in stock_text
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_matches = WEIGHT_PATTERN.findall(title)
    weight_g = int(weight_matches[-1]) if weight_matches else None

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
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_item_list()
    filtered = [
        it for it in items
        if not any(kw in it["title"] for kw in NON_BEAN_KEYWORDS)
    ]
    canonical_items = pick_canonical_items(filtered)

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
    with open("data_nadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nadacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
