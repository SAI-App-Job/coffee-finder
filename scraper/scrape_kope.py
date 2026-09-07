# -*- coding: utf-8 -*-
"""
scrape_kope.py

焙煎工房コペ(coffeeroastery-kope.com、三重県名張市松崎町1460-4、
自家焙煎スペシャルティコーヒーのオンライン販売)の商品情報を取得する。
WordPress独自テーマ(汎用のBASE/カラーミー/Shopify等ではない)。

【プラットフォームについて】
実データ確認済み: 商品カタログ自体はWordPressのカスタム投稿タイプ
(`/item/<スラッグ>/`)で構築され、商品名・価格(税込)が静的HTMLとして
サーバーサイドでレンダリングされている。購入ボタンのみSTORES.jpの
埋め込みウィジェット(`storesjp-button`、`btn.stores.jp/button.js`)を
利用しているが、これはあくまで決済/カート機能の埋め込みであり、
商品名・価格等の一覧情報自体はWordPress側の静的HTMLに存在するため
通常のHTTP GETで取得可能(本プロジェクトで対象外としているSTORES.jp
単体構築のSPA型ショップとは異なる)。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/のみ
Disallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う公開商品
ページは制限対象外。

【商品情報の取得方法について】
実データ確認済み: <title>タグは店名を含む定型文言のみで商品名を
含まないため使用不可。og:titleメタタグは実際の商品名を含むが、末尾に
" - 名張のコーヒーショップ | 焙煎工房コペ"という店舗共通のサフィックスが
全商品ページで付与されていることを実データで再確認した(2026-09-07)。
このサフィックスを" - "区切りで除去してから商品名として使用する
(商品名自体に日本語の"|"区切りが含まれるため、除去は先頭からの
" - 名張のコーヒーショップ"以降のみを対象とし、"|"では分割しない)。価格は
`<p class="SingItem-Com SingItem-Price">2150<span class="Small">
円（税込）</span></p>`のように数字がそのままテキストノードとして
入っているため、CSSセレクタ.SingItem-Priceのテキストから先頭の
数字部分を取得する。在庫状態を示す構造化フラグは実データ確認の範囲
(9商品全件)で見つからなかったため、商品名のテキストのみから
detect_stock_status()で判定する。

【商品一覧の取得方法について】
実データ確認済み: /item/ のアーカイブページ1ページに全9商品が掲載されて
おり、ページネーションは無い。

【非コーヒー豆商品の除外について】
実データ確認済み(全9件): 「LIQUID COFFEE(VENEZUELA)」のみ瓶詰めの
リキッドコーヒーでコーヒー豆単品ではないため除外(タイトルに重量表記
「100g」が無く、"LIQUID"を含むことで判別可能)。残り8件
(いずれも100gまたは200gのスペシャルティコーヒー豆)を対象とする。
産地は英語表記(ECUADOR/VENEZUELA/COLOMBIA/ETHIOPIA/BRAZIL)のため
coffee_parser.ORIGIN_COUNTRY_KEYWORDS_ENで検出を試みるが、
ベネズエラ(Venezuela)は同辞書に未登録のため該当商品はorigin_country
がNoneのまま出力される(既存の辞書マスタの更新はスクレイパー実装の
範囲外のため、本ファイルでは対応しない)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "焙煎工房コペ",
    "url": "https://coffeeroastery-kope.com/",
    "platform": "WordPress(独自テーマ、決済のみSTORES.jp埋め込み)",
    "address": "三重県名張市松崎町1460-4",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/のみDisallow、"
                          "本スクレイパーが使う公開商品ページは制限対象外)",
}

BASE_URL = "https://coffeeroastery-kope.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["LIQUID"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"(\d[\d,]*)")
TITLE_SUFFIX_PATTERN = re.compile(r"\s*-\s*名張のコーヒーショップ\s*\|\s*焙煎工房コペ\s*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_title(soup: BeautifulSoup) -> str:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return ""
    raw = title_el["content"].strip()
    return TITLE_SUFFIX_PATTERN.sub("", raw).strip()


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/item/")
    urls: set[str] = set()
    for a in soup.select(f'a[href^="{BASE_URL}/item/"]'):
        href = a.get("href", "")
        if re.match(rf"^{re.escape(BASE_URL)}/item/[a-z0-9-]+/$", href):
            urls.add(href)
    return sorted(urls)


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title = extract_title(soup)
    if not title or any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one("p.SingItem-Price")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

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
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title = extract_title(soup)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(soup, product_url)
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
    with open("data_kope.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kope.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
