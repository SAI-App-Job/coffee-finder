# -*- coding: utf-8 -*-
"""
scrape_kogetsuan.py

香月庵ネットショップ(kogetsuan.raku-uru.jp、京都府向日市、約200年続く
竹材業者が2021年より自家焙煎コーヒーを開始したオンライン販売)の商品
情報を取得する。楽々シリーズ(Raku-Uru)、このプロジェクト初対応の
プラットフォーム。カラーミーショップとは別の独立したカート基盤で、
`var Colorme = {...}` は埋め込まれておらず、商品一覧・詳細ページは
サーバーサイドレンダリングの静的HTML(/item-list?categoryId=N、
/item-detail/<id>)。

robots.txt確認済み(2026-09時点): /robots.txtへのアクセスはHTTP 404
(サイト自前の404ページが返る=robots.txt自体が存在しない)。明示的な
Disallow指定が無いため、実質的に制限なしと判断した。

【カテゴリ構造について】
実データ確認済み: 全6カテゴリ(京都・乙訓 朝掘り筍・惣菜・一品・ご飯の素・
梅こぶ茶・その他・ギフト・自家焙煎コーヒー豆)のうち「自家焙煎コーヒー豆」
(categoryId=108822)のみが対象。全11件、ページネーションなし(1ページに
全件表示)。

【重量について】
実データ確認済み: 全11件とも内容量は100gで統一(商品詳細ページ下部の
「内容量 : 100g」表記で確認)。重量違いの重複商品は存在しない。

【在庫状況について】
実データ確認済み: 商品詳細ページのカートフォーム内、在庫がある場合は
`<a href="#" class="raku-add-cart">カートに入れる</a>`のカートボタンが
表示されるが、品切れの場合はこのボタンが無く、代わりに
`<div class="item-dtail-orderinvalid">ただいまご注文いただけません。</div>`
が表示される(実データ確認済み、全11件中1件「ンゴロンゴロAA++」がこの
状態)。この構造化フラグで在庫判定する。

【非コーヒー豆商品の除外について】
実データ確認済み: 全11件すべてがストレート/ブレンドのコーヒー豆(内
「カフェインレス」1件はデカフェ)で、非対象商品は無かった。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "香月庵",
    "url": "https://kogetsuan.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "京都府向日市寺戸町梅ノ木1-2 香月栖1階",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(2026-09確認。/robots.txtはHTTP 404で"
                          "存在せず、明示的なDisallow指定が無いため制限なしと判断)",
}

BASE_URL = "https://kogetsuan.raku-uru.jp"
COFFEE_CATEGORY_ID = "108822"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS: list[str] = []
WEIGHT_PATTERN = re.compile(r"内容量\s*[:：]\s*(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_ids() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/item-list?categoryId={COFFEE_CATEGORY_ID}")
    ids = []
    for a in soup.select('p.item-name a[href^="/item-detail/"]'):
        href = a.get("href", "")
        item_id = href.rsplit("/", 1)[-1]
        if item_id and item_id not in ids:
            ids.append(item_id)
    return ids


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one("div.item-head h1.title1")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_el = soup.select_one("b.raku-item-vari-price-num")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    weight_g = None
    footer_el = soup.select_one("div.item-footer")
    if footer_el:
        m = WEIGHT_PATTERN.search(footer_el.get_text())
        if m:
            weight_g = int(m.group(1))

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

    has_orderinvalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    has_add_cart = soup.select_one("a.raku-add-cart") is not None
    structural_out_of_stock = has_orderinvalid and not has_add_cart
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
    item_ids = fetch_item_ids()

    records = []
    flavored_records = []
    for item_id in item_ids:
        product_url = f"{BASE_URL}/item-detail/{item_id}"
        try:
            detail = build_record(fetch_page(product_url), product_url)
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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kogetsuan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kogetsuan.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
