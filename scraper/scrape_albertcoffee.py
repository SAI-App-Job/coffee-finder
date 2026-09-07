# -*- coding: utf-8 -*-
"""
scrape_albertcoffee.py

Albert Coffee Roasters(albert-coffee.com/shop/、愛知県名古屋市西区上小田井
2丁目181、自家焙煎豆のオンライン販売)の商品情報を取得する。EC-CUBE
(WordPressサイトのサブディレクトリ/shop/にEC-CUBEを設置)。

【プラットフォームについて】
候補リストではShopifyと予想されていたが、実データ確認の結果、
albert-coffee.com自体はWordPressで、実店舗情報ページ(/shop-2/)・
オンラインショップ入口ページ(/online-shop/)を持つ。オンラインショップ
入口ページの「公式オンラインショップへ」リンクは/shop/(EC-CUBE、eccube
セッションCookieを確認済み)を指しており、本スクレイパーはこちらを対象と
する。なお別途albert-coffee.myshopify.comというShopifyドメインも存在し
実際に稼働中の商品データを持つが、店舗のサイト自身が案内する「公式」の
入口ではないため対象外とした(旧または並行運用の可能性があるが未確認)。
本サイトはEC-CUBE、malki-coffeeと同じ煎豆屋(EC-CUBE)系統のためirimameya
/malki-coffeeと類似の実装。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/等の管理系
パスのみDisallow(WordPress標準)。/shop/配下は制限対象外。

【商品一覧の取得方法について】
実データ確認済み: カテゴリ「珈琲豆」(category_id=1)に焙煎豆単品の全14件
がまとまっている。「大容量」(category_id=14、業務用2kgサイズの重複
商品)・「メール便」(category_id=15、ドリップバッグ/アソートセット/
汎用配送商品)・「お試し」(category_id=16、複数銘柄詰め合わせの
お試しセット)・「限定品」「アウトレット」に含まれる業務用重複・詰め
合わせ・ドリップバッグ・リキッドコーヒーは全てcategory_id=1に含まれない
別商品であることを確認済みのため、category_id=1のみを巡回すればよい。

【非コーヒー豆商品の除外について】
実データ確認済み: category_id=1の14件は全て単一銘柄の焙煎豆(ストレート
+アルバートブレンド2種)で、非対象商品は含まれない。

【重量・価格・在庫の取得について】
実データ確認済み: 各商品ページに埋め込まれたEC-CUBE標準のJS変数
`eccube.classCategories`から重量・挽き方の組み合わせごとの
price02_inc_tax(税込価格)とstock_find(在庫有無)を取得する(丸喜と同じ
方式)。ただし丸喜と異なり、本店では classcategory_id1(外側キー)が
「豆のまま/挽いた状態」の挽き方、classcategory_id2(内側リーフ)が
「100g/250g/500g」の重量というネスト順序が逆になっている(店舗ごとの
EC-CUBE管理画面設定次第で順序が異なることを実データで確認)。また
「期間限定【エルサルバドル】250g」のように商品名に重量が直接明記されて
おり、classCategoriesのリーフにも重量情報が無いケースも存在する。この
ため、まず商品名から重量を抽出し、無ければclassCategories内の全リーフを
走査して(挽き方/重量どちらが外側キーでも対応できるよう)名前が
「NNNg」形式に一致するリーフを重量情報として使う汎用ロジックを採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Albert Coffee Roasters",
    "url": "https://albert-coffee.com/shop/",
    "platform": "EC-CUBE",
    "address": "愛知県名古屋市西区上小田井2丁目181",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。WordPress標準のrobots.txtで"
                          "/wp-admin/等の管理系パスのみDisallow。/shop/配下は"
                          "制限対象外)",
}

BASE_URL = "https://albert-coffee.com/shop"
BEAN_CATEGORY_ID = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
CLASS_CATEGORIES_MARKER = "eccube.classCategories = "


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/products/list?category_id={BEAN_CATEGORY_ID}")
    pids: set[str] = set()
    for a in soup.select('a[href*="/products/detail/"]'):
        m = re.search(r"/products/detail/(\d+)", a.get("href", ""))
        if m:
            pids.add(m.group(1))
    return [f"{BASE_URL}/products/detail/{pid}" for pid in sorted(pids, key=int)]


def extract_class_categories(html_text: str) -> dict:
    idx = html_text.find(CLASS_CATEGORIES_MARKER)
    if idx == -1:
        return {}
    i = idx + len(CLASS_CATEGORIES_MARKER)
    while i < len(html_text) and html_text[i] != "{":
        i += 1
    start = i
    depth = 0
    for i in range(start, len(html_text)):
        if html_text[i] == "{":
            depth += 1
        elif html_text[i] == "}":
            depth -= 1
            if depth == 0:
                i += 1
                break
    try:
        return json.loads(html_text[start:i])
    except json.JSONDecodeError:
        return {}


def flatten_leaves(class_categories: dict) -> list[dict]:
    leaves = []
    for outer_key, inner in class_categories.items():
        if outer_key == "__unselected" or not isinstance(inner, dict):
            continue
        for inner_key, detail in inner.items():
            if inner_key == "#" or not isinstance(detail, dict) or not detail.get("product_class_id"):
                continue
            leaves.append(detail)
    return leaves


def pick_canonical_leaf(leaves: list[dict]) -> tuple[dict | None, int | None]:
    if not leaves:
        return None, None

    def leaf_weight(d):
        m = WEIGHT_PATTERN.search(d.get("name") or "")
        return int(m.group(1)) if m else None

    weighted = [(leaf_weight(d), d) for d in leaves]
    weighted = [(w, d) for w, d in weighted if w is not None]
    if not weighted:
        return leaves[0], None

    in_stock = [(w, d) for w, d in weighted if d.get("stock_find")]
    pool = in_stock or weighted
    weight_g, detail = min(pool, key=lambda item: item[0])
    return detail, weight_g


def build_record(soup: BeautifulSoup, html_text: str, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    title = title_el["content"].strip() if title_el and title_el.get("content") else ""
    if not title:
        return None

    parsed = parse_product(title)
    class_categories = extract_class_categories(html_text)
    leaves = flatten_leaves(class_categories)

    title_weight_m = WEIGHT_PATTERN.search(title)
    if title_weight_m:
        weight_g = int(title_weight_m.group(1))
        in_stock_leaves = [d for d in leaves if d.get("stock_find")]
        detail = (in_stock_leaves or leaves or [None])[0]
    else:
        detail, weight_g = pick_canonical_leaf(leaves)

    price = None
    if detail is not None:
        price_text = (detail.get("price02_inc_tax") or "").replace(",", "")
        price = int(price_text) if price_text.isdigit() else None

    all_out_of_stock = bool(leaves) and not any(d.get("stock_find") for d in leaves)

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

    stock_status = detect_stock_status(title, all_out_of_stock)

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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html_text = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        soup = BeautifulSoup(html_text, "html.parser")
        detail = build_record(soup, html_text, product_url)
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
    with open("data_albertcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_albertcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
