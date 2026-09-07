# -*- coding: utf-8 -*-
"""
scrape_mochamocha.py

自家焙煎珈琲MochaMocha(mochamocha-coffee.com、愛知県豊田市大林町12-3-6、
自家焙煎豆のオンライン販売)の商品情報を取得する。WordPress独自投稿タイプ
(wc/store/v1のWooCommerce Store APIは404で存在せず、通常のWooCommerce商品
ではない)。

【プラットフォームについて】
実データ確認済み(2026-09時点): /wp-json/wc/store/v1/productsは404で
WooCommerce Store APIは無い。実際は「item」というカスタム投稿タイプ
(パーマリンク/archives/item/<slug>)で商品ページを作っており、公開REST API
(/wp-json/wp/v2/item)から全件取得できる。商品ページ自体には「カートに
入れる」ボタンがあり、フォームのaction先は外部カートサービス
「cart.raku-uru.jp」(楽うるカート)。一覧・商品情報の取得はこのカート
サービスに一切アクセスせず、REST APIのcontent.rendered(投稿本文HTML、
サーバー側で完全にレンダリング済み、JS実行不要)を読むだけで完結するため
実装対象とする。

robots.txt確認済み: 標準的なWordPressのrobots.txt(/wp-admin/のみ
Disallow、admin-ajax.phpは個別にAllow)。本スクレイパーが使うREST API・
商品ページは制限対象外。

【対象投稿の絞り込みについて】
実データ確認済み(全24件): 「item」投稿タイプにはコーヒー豆(ストレート14件+
ブレンド2件)の他に、ドリップバッグ5件(dripbag01〜05)・水出しコーヒー
パック1件(coldbrewpack)が混在している。ドリップバッグ・水出しパックは
焙煎豆単品ではないためNON_BEAN_KEYWORDSで除外する。

【重量・価格の取得方法について】
実データ確認済み(2026-09再確認): 当初「【100g】　販売価格：X円」が本文中に
直接連続して出現すると想定していたが、実際のHTML構造は
`<h2>【100g】</h2>` 見出しの後に(スペーサーや`<form action="...raku-uru...">`
タグを挟んで)`<div class="raku-cart-itemname">販売価格：X円（税込み）</div>`
が続く形で、両者の間に十分な量のマークアップが挟まるため単純な文字列
正規表現(見出しと価格が直接隣接する前提)では抽出できない。またコーヒー豆
商品は100gの他に「【500g入り1パック】100円お得です♪」という2サイズ目も
併売しており、当初の想定(全商品100gの単一サイズのみ)は誤りだった。
実データ確認済み(コーヒー豆全18件): `<h2>`要素のうち「【数字g」で始まる
テキストと、`<div class="raku-cart-itemname">`要素のうち「販売価格」を含む
テキストが、出現順で1対1に対応する(1番目のh2=100g見出しに対し1番目の
価格divが100gの価格、2番目のh2=500gパック見出しに対し2番目の価格divが
500gパックの価格)ことを全18件で確認済み。ブレンド2商品(ビターブレンド・
午後のブレンド)には上記2つの重量見出しの後に「簡単で美味しい
アイスコーヒー/カフェオレの作り方」という無関係な`<h2>`が追加で
出現するが、重量パターンにマッチしないため誤検出しない。
BeautifulSoupでcontent.renderedを再パースし、`<h2>`群と
`<div class="raku-cart-itemname">`群をそれぞれ出現順に集めてzipで
対応付け、最小重量(100g)のペアを採用する。

【焙煎度について】
商品名(【売り切れ】〔浅煎り〕等)には浅煎り/中煎り/深煎り等の粗い表記が
含まれる商品もあるが、値が本文の自由記述(例:「【浅煎り】と【中深煎り】に
煎り分けてブレンド」)に埋め込まれており商品ごとの構造化された単一値として
取り出しにくいため、他店のマンデリンあのころ等と同様にroast_levelは
商品名解析(parse_product)任せとし、本文からの個別抽出は行わない。

【在庫状態について】
実データ確認済み: 商品名先頭に「【売り切れ】」「【入荷待ち】」という
prefixが付く商品があり、いずれもcoffee_parserのSTOCK_STATUS_SYNONYMS
(「一時的に品切れ」に分類済み)でそのまま検出できる。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎珈琲MochaMocha",
    "url": "https://mochamocha-coffee.com/",
    "platform": "WordPress独自投稿タイプ(商品ページに楽うるカート(cart.raku-uru.jp)"
                "の購入フォームを埋め込み。一覧・商品情報はwp-json REST APIから取得)",
    "address": "愛知県豊田市大林町12-3-6",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なWordPressのrobots.txt。"
                          "/wp-admin/のみDisallow、admin-ajax.phpは個別にAllow)",
}

API_URL = "https://mochamocha-coffee.com/wp-json/wp/v2/item"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "水出しコーヒーパック"]
WEIGHT_HEADING_PATTERN = re.compile(r"【(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"販売価格[：:]\s*([\d,]+)円")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return HTML_TAG_PATTERN.sub(" ", text or "")


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        if resp.status_code == 400:
            break  # ページ範囲外(rest_post_invalid_page_number)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def extract_min_weight_price_pair(content_html: str) -> tuple[int | None, int | None]:
    """理由はモジュールdocstring参照(重量見出しの<h2>群と価格の
    <div class="raku-cart-itemname">群を出現順にzipで対応付け、
    最小重量のペアを採用する)。"""
    soup = BeautifulSoup(content_html, "html.parser")
    weights = []
    for h2 in soup.find_all("h2"):
        m = WEIGHT_HEADING_PATTERN.search(h2.get_text())
        if m:
            weights.append(int(m.group(1)))
    prices = []
    for div in soup.find_all("div", class_="raku-cart-itemname"):
        m = PRICE_PATTERN.search(div.get_text())
        if m:
            prices.append(int(m.group(1).replace(",", "")))
    pairs = list(zip(weights, prices))
    if not pairs:
        return None, None
    return min(pairs, key=lambda p: p[0])


def build_record(product: dict) -> dict | None:
    name = (product.get("title") or {}).get("rendered", "").strip()
    name = strip_html(name).strip()
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    content_html = (product.get("content") or {}).get("rendered", "")
    weight_g, price = extract_min_weight_price_pair(content_html)
    product_url = product.get("link")

    parsed = parse_product(name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
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
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_mochamocha.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mochamocha.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
