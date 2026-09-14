# -*- coding: utf-8 -*-
"""
scrape_juncoffee.py

珈琲自家焙煎工房 juncoffee(store.shopping.yahoo.co.jp/juncoffee、高知県
高知市大津乙3-10、自家焙煎豆のオンライン販売)の商品情報を取得する。
Yahoo!ショッピング。本プロジェクトで初めて対応するYahoo!ショッピング
単体ストア(モール出店のみで自社ECサイトを持たない形態)。

【プラットフォームについて】
実データ確認済み(2026-09時点): Yahoo!ショッピングの店舗カテゴリページ
(例: https://store.shopping.yahoo.co.jp/juncoffee/e0dde0eac62.html)は
Next.jsによるサーバーサイドレンダリングで、`<script id="__NEXT_DATA__"
type="application/json" crossorigin="anonymous">`内のJSONに商品名・価格・
重量(weight)・URLが構造化データとして埋め込まれている
(props.initialState.bff.searchResults.items."1"[1].content.items)。
JS実行なしで通常のHTTP GETから全件取得できる。

【住所について】
juncoffee自身のYahoo!ショッピング店舗ページには特定商取引法の記載欄が
見当たらなかったため、juncoffeeの自社ブログサイト(juncoffee.jp、Yahoo!
ショッピングの購入ページへの誘導リンクのみで通販機能自体は持たない)の
特定商取引法ページ(https://juncoffee.jp/?page_id=2629)で実データ確認
したところ「〒781-5103 高知県高知市大津乙3-10」との記載を確認した
(一次情報)。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): store.shopping.yahoo.co.jpのrobots.txt
はUser-agent: *に対し/cgi-bin/・/search.html(一部クエリ)等のみDisallow。
本スクレイパーが使うカテゴリページ(例: /e0dde0eac62.html)は制限対象外。

【カテゴリ構造と重量違いの重複について】
実データ確認済み: 「珈琲豆(200g袋)」(srid=e0dde0eac62、18件)と「珈琲豆
(小分け袋)」(srid=e0dde0eac63、18件)の2カテゴリがあり、後者は前者と全く
同じ18銘柄の100g版(小分け袋)。他店舗と同じ「最小重量を代表として採用」の
方針に基づき、100g版のみを対象とする(200g版は除外)。

【焙煎度違いについて】
実データ確認済み: 「タンザニア／ジェニュイン・キリマンジャロ」のように
同一産地が［ミディアム］［フルシティ］等、異なる焙煎度で複数商品として
登録されている場合がある。これは重量違いの重複とは異なり、焙煎度という
別の商品特性を表すため、重複統合せずそれぞれ独立した商品として扱う。

【商品名について】
実データ確認済み(全18件): ストレート銘柄は「産地／農園名［焙煎度］
(重量)」形式、ブレンドは「銘柄名ブレンド(重量)」形式。全てコーヒー豆
単品で、非コーヒー豆商品は無かった。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲自家焙煎工房 juncoffee",
    "url": "https://store.shopping.yahoo.co.jp/juncoffee/",
    "platform": "Yahoo!ショッピング",
    "address": "高知県高知市大津乙3-10",
    "prefecture": "高知県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *は/cgi-bin/・"
                          "/search.html(一部クエリ)等のみDisallow。本スクレイパーが"
                          "使うカテゴリページは制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/juncoffee"
# 理由はモジュールdocstring参照(小分け袋=100g版のみを対象とし、200g版は
# 重量違いの重複として除外する)
CATEGORY_URL = f"{BASE_URL}/e0dde0eac63.html"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}

NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_category_items() -> list[dict]:
    resp = requests.get(CATEGORY_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    text = resp.content.decode("utf-8")
    m = NEXT_DATA_PATTERN.search(text)
    if not m:
        return []
    import json

    data = json.loads(m.group(1))
    try:
        search_results = data["props"]["initialState"]["bff"]["searchResults"]["items"]["1"][1]["content"]["items"]
    except (KeyError, IndexError, TypeError):
        return []
    return search_results


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    price = item.get("price")
    product_url = (item.get("url") or "").split("?")[0] or item.get("quickView", {}).get("url", "").split("?")[0]
    weight_g = item.get("weight")
    if weight_g is None:
        weight_m = WEIGHT_PATTERN.search(title)
        weight_g = int(weight_m.group(1)) if weight_m else None

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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_category_items()

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
    with open("data_juncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_juncoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
