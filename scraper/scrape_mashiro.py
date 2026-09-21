# -*- coding: utf-8 -*-
"""
scrape_mashiro.py

珈琲豆ましろ(coffeebeans-mashiro.com、〒722-0073 広島県尾道市向島町
5557-17、自家焙煎豆のオンライン販売)の商品情報を取得する。EC Force
(本プロジェクト初のEC Force店舗)。

【プラットフォームについて】
実データ確認済み: URL構造(/shop/products/<SKU>、/shop/product_categories/
<slug>)、CDN配信元(cloudfront.net、パスに"ec_assets"を含む)から
EC Forceと判断した。カテゴリ一覧ページに商品名・価格が静的HTMLでそのまま
出力されており(JS実行不要)、低リスクな抽出方法として実装する。

robots.txt確認済み(2026-09時点): コメントアウトされたUser-agent: *の
Disallow: /のみで実際には無効化されており、実質的な制限記述が無い
(コメント文中の説明のみ)。Sitemap行の記載あり。

【対象カテゴリについて】
実データ確認済み: 商品カテゴリは「coffee-beans(珈琲豆、ブレンド/
シングルオリジン)」「cafe-au-lait-base(カフェオレベース)」
「dankcoffeebag(暖コーヒーバッグ)」「gift(ギフト)」「icedcoffee(アイス
コーヒー)」「mizudashi(水出し)」「tanoshi(?)」の7種類。coffee-beans
カテゴリの8件のみが対象で、それ以外はいずれも非コーヒー豆・別形態の
商品(実データ確認済み、カテゴリ名から自明)。

【商品情報の取得方法について】
実データ確認済み: coffee-beansカテゴリ一覧ページの各商品カードは
div.c-product_item__inner__titleに商品名(先頭に「［珈琲豆200g～］」の
定型プレフィックス付き)、同カード内の価格表示(税込)がそのまま入っている。
商品詳細ページはJSで大部分がレンダリングされ重量バリエーションの構造が
静的HTMLから読み取れなかったため、一覧ページの表示価格(200g基準、
実データ確認済みで全8件が同額1,701円)をそのまま採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: coffee-beansカテゴリ8件はいずれも「［珈琲豆200g～］」
プレフィックス付きの実際のコーヒー豆(ブレンド4種+シングルオリジン
[インドネシア・ブラジル・カフェインレスグアテマラ・エチオピア
ウォッシュト/ナチュラルの2種]4種)で、除外対象の商品は無い。

【在庫状況について】
実データ確認済み: 一覧ページ・詳細ページのいずれにも構造化された
売り切れバッジは確認できなかった(2026-09時点で全件在庫あり)ため、
商品名のテキストのみから判定する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionは全商品共通の店舗紹介文で商品固有の
情報を含まないため使用しない。代わりに商品詳細ページのdiv#product-
description(div.c-product_info__description)を使うと対象8件全てで
テイスティング文が入っていることを確認した。注文/配送案内等の無関係な
定型文の混入は無いため全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲豆ましろ",
    "url": "https://coffeebeans-mashiro.com/",
    "platform": "EC Force",
    "address": "広島県尾道市向島町5557-17",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txtのDisallow: /行はコメントアウト"
                          "されており実際には無効。実質的な制限記述なし)",
}

BASE_URL = "https://coffeebeans-mashiro.com"
CATEGORY_URL = f"{BASE_URL}/shop/product_categories/coffee-beans"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TITLE_PREFIX_PATTERN = re.compile(r"^［珈琲豆\s*\d+\s*[gｇ]\s*[~～]\s*］\s*")
WEIGHT_PATTERN = re.compile(r"\d+\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div#product-description")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    return text.strip() or None


def fetch_items() -> list[dict]:
    soup = fetch_page(CATEGORY_URL)
    items = []
    for card in soup.select("div.c-product_item"):
        link_el = card.select_one('a.c-product_item__link[href^="/shop/products/"]')
        title_el = card.select_one("div.c-product_item__inner__title")
        price_el = card.select_one("div.c-product_item__inner__price span")
        if not link_el or not title_el:
            continue
        raw_title = title_el.get_text(strip=True)
        title = TITLE_PREFIX_PATTERN.sub("", raw_title).strip()
        weight_m = WEIGHT_PATTERN.search(raw_title)
        weight_g = int(re.sub(r"[^\d]", "", weight_m.group(0))) if weight_m else None
        price = None
        if price_el:
            price_m = PRICE_PATTERN.search(price_el.get_text())
            if price_m:
                price = int(price_m.group(1).replace(",", ""))
        product_url = BASE_URL + link_el["href"]
        try:
            flavor_notes = extract_flavor_notes(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            flavor_notes = None
        items.append({
            "title": title,
            "weight_g": weight_g,
            "price": price,
            "flavor_notes": flavor_notes,
            "url": product_url,
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if not title:
        return None
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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_items()

    records = []
    flavored_records = []
    for item in items:
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
    with open("data_mashiro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mashiro.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
