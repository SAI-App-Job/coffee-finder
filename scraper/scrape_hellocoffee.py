# -*- coding: utf-8 -*-
"""
scrape_hellocoffee.py

ハローコーヒー自家焙煎コーヒー工房(store.shopping.yahoo.co.jp/
hellocoffee-proshop、青森県弘前市大字代官町58-1、自家焙煎豆のオンライン
販売)の商品情報を取得する。Yahoo!ショッピング単体ストア(juncoffeeに続き
本プロジェクト2例目)。

【住所について】
店舗情報ページ(https://store.shopping.yahoo.co.jp/hellocoffee-proshop/
info.html#storeinfo)で実データ確認済み(2026-09時点): 「青森県弘前市大字
代官町58-1」との記載を確認。候補リストの住所と一致。

robots.txt確認済み(2026-09時点、juncoffeeと同じ): store.shopping.yahoo.
co.jpのrobots.txtはUser-agent: *に対し/cgi-bin/・/search.html(一部
クエリ)等のみDisallow。本スクレイパーが使うsearch.htmlはクエリパラメータ
の組み合わせにより該当しない(検証済み)。

【商品構成について】
実データ確認済み: 店舗全体でキーワード「コーヒー豆」を検索すると72件
ヒットするが、大半は自家焙煎済みの豆ではなく家庭用ロースター向けの
「コーヒー生豆」(未焙煎の生豆、本プロジェクトの対象外)であることが商品
タイトルから判明した。一方、キーワード「自家焙煎」で店内検索すると
15件にヒットし、全件が実際に自家焙煎された豆(マンデリン・プレミアム
ブレンド・キリマンジャロ・スペシャルブレンドII・アイスブレンド・ホテル・
レストランブレンド・ロイヤルフレンチロースト)であることを実データ確認
した。このため「自家焙煎」キーワード検索結果を対象商品の一覧として採用
する。

【検索結果JSONの文字化けについて】
実データ確認済み: 検索結果ページ(search.html)の`__NEXT_DATA__`内JSON
(bff.searchResults)に含まれる商品名・価格のテキストが文字化けしている
(店舗側のデータ登録時のエンコーディング不整合と推定)。URLフィールドのみ
正しくデコードできるため、これを使って個別商品ページを取得し、そちらの
OGPメタタグ(`og:title`・`product:price:amount`)から正しい商品名・価格を
取得する(他のBASE系店舗と同じ方式)。

【重量について】
実データ確認済み: 商品名に全角混じりで「１ｋｇ」「３ｋｇ」「５００ｇ×2袋」
等の重量表記がある。NFKC正規化後、「(数字)g×(数字)」の掛け算表記→
「(数字)kg」→「(数字)g」の優先順で検出する。

【重量違いの重複について】
実データ確認済み: マンデリン(1/2/3kg)・プレミアムブレンド(1/3/5kg)・
キリマンジャロ(1/2/3kg)がそれぞれ複数の重量で個別商品登録されている。
重量表記を除いた基準名でグルーピングし、最小重量を代表として採用する
(店舗側の表記ゆれにより一部完全には統合されない場合がある)。

【非コーヒー豆商品の除外について】
実データ確認済み: 「選べるブレンドコーヒー豆　フレンチロースト　５００ｇ
ｘ2種類」のみ、特定のブレンド名が無く複数銘柄から選ぶ形式のため対象外
(NON_BEAN_KEYWORDSで除外)。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ハローコーヒー自家焙煎コーヒー工房",
    "url": "https://store.shopping.yahoo.co.jp/hellocoffee-proshop/",
    "platform": "Yahoo!ショッピング",
    "address": "青森県弘前市大字代官町58-1",
    "prefecture": "青森県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *は/cgi-bin/・"
                          "/search.html(一部クエリ)等のみDisallow。本スクレイパーが"
                          "使うクエリの組み合わせは制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/hellocoffee-proshop"
SEARCH_URL = f"{BASE_URL}/search.html?p={quote('自家焙煎')}"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["種類"]
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
WEIGHT_MULT_PATTERN = re.compile(r"(\d+)\s*g\s*[×xX]\s*(\d+)")
WEIGHT_KG_PATTERN = re.compile(r"(\d+)\s*kg")
WEIGHT_G_PATTERN = re.compile(r"(\d+)\s*g")


def fetch_search_item_urls() -> list[str]:
    resp = requests.get(SEARCH_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    m = NEXT_DATA_PATTERN.search(resp.text)
    if not m:
        return []
    data = json.loads(m.group(1))
    try:
        search_results = data["props"]["initialState"]["bff"]["searchResults"]["items"]["1"][1]["content"]["items"]
    except (KeyError, IndexError, TypeError):
        return []
    return [item["url"].split("?")[0] for item in search_results if item.get("url")]


def fetch_product_fields(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', resp.text)
    if not title_m:
        return None
    title = title_m.group(1).split(" : ")[0].strip()
    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', resp.text)
    price = int(float(price_m.group(1))) if price_m else None
    return {"title": title, "price": price}


def detect_weight(normalized_title: str) -> int | None:
    m = WEIGHT_MULT_PATTERN.search(normalized_title)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = WEIGHT_KG_PATTERN.search(normalized_title)
    if m:
        return int(m.group(1)) * 1000
    m = WEIGHT_G_PATTERN.search(normalized_title)
    return int(m.group(1)) if m else None


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        normalized_title = unicodedata.normalize("NFKC", item["title"])
        base_name = WEIGHT_MULT_PATTERN.sub("", normalized_title)
        base_name = WEIGHT_KG_PATTERN.sub("", base_name)
        base_name = WEIGHT_G_PATTERN.sub("", base_name)
        base_name = re.sub(r"[（）()]", "", base_name)
        base_name = re.sub(r"\s+", " ", base_name).strip()
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_key = existing["weight_g"] if existing and existing["weight_g"] is not None else float("inf")
        if existing is None or weight_key < existing_weight_key:
            by_base_name[base_name] = item
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
    item_urls = fetch_search_item_urls()

    all_items = []
    for url in item_urls:
        try:
            fields = fetch_product_fields(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        normalized_title = unicodedata.normalize("NFKC", title)
        weight_g = detect_weight(normalized_title)
        all_items.append({"title": title, "price": fields["price"], "weight_g": weight_g, "url": url})

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_hellocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hellocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
