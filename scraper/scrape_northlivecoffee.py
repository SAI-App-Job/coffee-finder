# -*- coding: utf-8 -*-
"""
scrape_northlivecoffee.py

ノースライブコーヒー(northlivecoffee.raku-uru.jp、北海道江別市野幌町
53-20、楽々シリーズ/Raku-Uru)の商品情報を取得する。

住所は特定商取引法ページ(https://northlivecoffee.raku-uru.jp/law)で実データ
確認済み(2026-09時点、〒069-0813 北海道江別市野幌町53-20)。

【プラットフォームについて】
香月庵(scrape_kogetsuan.py)と同じRaku-Uruだが別テーマ。一覧ページの
div.product-list-item内に商品名(p.product-list-name)・価格
(span.product-list-num)が完結しており、詳細ページへのアクセスは不要。
香月庵で使われていたp.item-name/raku-add-cart等の在庫構造化フラグは
本テーマには存在しないため、商品名テキスト中の「※完売」等の表記(実データ
確認済み、キューバ・クリスタルマウンテンで使用)のみで在庫判定する。

【対象カテゴリについて】
実データ確認済み: 「●ストレートコーヒー」(categoryId=8320、12件)・
「●ブレンドコーヒー」(categoryId=8319、14件)・「●カフェインレスコーヒー」
(categoryId=10828、6件)の計32件を対象とする。「アジア」「アフリカ」等の
産地別カテゴリ、「浅煎り」等の焙煎度別カテゴリは上記3カテゴリの商品を
横断的に再分類したタグに過ぎないと判断し重複回避のため対象外。「●ギフト
セット」「●ドリップバッグコーヒー」「●紅茶」「●黒豆茶」「羊蹄山麓湧水
ｱｲｽｺｰﾋｰ」「ﾁｰｽﾞｹｰｷ・焼菓子・菓子類」も非対象。カフェインレスコーヒー
カテゴリ内の「カフェインレスブレンドドリップバッグ」もドリップバッグ単品
のため除外する。

【重量について】
実データ確認済み: 大半は商品名に「（200g）」表記があるが、一部
「カフェインレスブレンド 100g×1」「同 100g×2」のように基本量×個数の
表記がある。「100g×2」のような表記は正規表現で基本量と個数を掛け合わせて
総重量を算出する。

robots.txt確認済み(2026-09時点): /robots.txt自体が存在しない(404)。
明示的なDisallow指定が無いため実質制限なしと判断した。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ノースライブコーヒー",
    "url": "https://northlivecoffee.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "北海道江別市野幌町53-20",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。/robots.txtはHTTP 404で"
                          "存在せず、明示的なDisallow指定が無いため制限なしと判断)",
}

BASE_URL = "https://northlivecoffee.raku-uru.jp"
CATEGORY_IDS = [8320, 8319, 10828]  # ストレート・ブレンド・カフェインレス
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ"]
WEIGHT_MULTIPLY_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*[×xX]\s*(\d+)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_MULTIPLY_PATTERN.search(title)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def build_record(item) -> dict | None:
    name_el = item.select_one("p.product-list-name")
    a_el = item.select_one('a[href^="/item-detail/"]')
    if not name_el or not a_el:
        return None
    title = name_el.get_text(strip=True)
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    product_url = f"{BASE_URL}{a_el['href']}"

    price_el = item.select_one("span.product-list-num")
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    parsed = parse_product(title)

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
        "weight_g": parse_weight_g(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records_by_url: dict[str, dict] = {}
    flavored_by_url: dict[str, dict] = {}

    for cat_id in CATEGORY_IDS:
        url = f"{BASE_URL}/item-list?categoryId={cat_id}"
        try:
            soup = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            continue
        for item in soup.select("div.product-list-item"):
            detail = build_record(item)
            if detail is None:
                continue
            if detail.get("is_flavored"):
                flavored_by_url.setdefault(detail["product_url"], detail)
            else:
                records_by_url.setdefault(detail["product_url"], detail)

    return list(records_by_url.values()), list(flavored_by_url.values())


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_northlivecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_northlivecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
