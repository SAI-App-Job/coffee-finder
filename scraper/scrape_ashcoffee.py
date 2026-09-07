# -*- coding: utf-8 -*-
"""
scrape_ashcoffee.py

ASH COFFEE(ash-coffee.jp、静岡県掛川市上西郷1035-7、ピーベリー(丸豆)専門の
自家焙煎豆のオンライン販売)の商品情報を取得する。

【重要な訂正】依頼時の候補リストでは「店頭販売のみ(通販機能なし)」との
前提で手動入力対象とされていたが、実データ確認(2026-09)の結果、
ash-coffee.jpは独自ASP基盤(xaas3.jp、URL構成/category/<ID>/・
/item/<SKU>/、商品詳細ページにschema.org Product形式のJSON-LDあり)に
よる実働のオンラインショップ(カート・会員登録機能あり)を運営していた
ため、手動入力ではなく本スクレイパーを実装する。一次情報を直接確認する
ことの重要性を踏まえ、前提を鵜呑みにせず実サイトで再確認した。

robots.txt確認済み(2026-09時点): /default/error/・/preview/のみDisallow、
それ以外は制限なし。

【カテゴリ構成について】
実データ確認済み: トップページの「CATEGORY」タイル(1豆種=1カテゴリ)で
category/1〜17の17カテゴリが固定的に案内されている(category/18以降は
存在せず、同じ空一覧テンプレートが返ることを確認済み)。1カテゴリ=1銘柄
(ピーベリー種のみを扱う専門店)で、各カテゴリページに200g/300g/400gの
重量違いが複数商品(別URL)として登録されている。2026-09時点でカテゴリ
1(ASHブレンド)・4(ボリビアpb)・6(コスタリカpb、「※準備中」表記)・
7(ガラパゴスpb)・9(バリpb)・12(ペルーオルキディアpb)・
13(ブルーマウンテンpb)の7カテゴリは「該当データがありません」で商品
未登録(準備中)のため、実際に商品が存在するのは10カテゴリ(ルワンダ・
タイチェンライ・東ティモール・キリマンジャロ・グァテマラ・
メキシコセスマッチ・ラオスティピカ・マンデリン・トラジャ・
パプアニューギニアの各ピーベリー、計26商品)のみ。カテゴリ一覧ページは
1ページに全商品(最大3件)が収まっており(実データ確認済み、ページネー
ション表記はあるが全件が1ページ目に表示される)、追加ページ取得は不要。

【重量違いの重複について】
実データ確認済み: 上記10銘柄のうち9銘柄が200g/300g/400gの3サイズ、
パプアニューギニアpbのみ200gの単一サイズで登録されている。商品名から
重量表記を除いた基準名でグルーピングし、最小重量(200g)を代表として
採用する(他のBASE系店舗と同じ汎用ロジック)。

【非コーヒー豆商品について】
実データ確認済み: 2026-09時点で全カテゴリがピーベリー種の焙煎豆のみ
(ギフト/器具/ドリップバッグ等の商品カテゴリは存在しない)ため、
NON_BEAN_KEYWORDSは設けていない。将来的に新カテゴリが追加された場合は
要再確認。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ASH COFFEE",
    "url": "https://www.ash-coffee.jp/",
    "platform": "独自ASP(xaas3.jp基盤、schema.org JSON-LD公開)",
    "address": "静岡県掛川市上西郷1035-7",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/・/preview/のみDisallow、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.ash-coffee.jp"
CATEGORY_IDS = list(range(1, 18))  # 理由はモジュールdocstring参照(1〜17の固定17カテゴリ)
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
JSONLD_PATTERN = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def collect_item_urls() -> list[str]:
    urls: set[str] = set()
    for cid in CATEGORY_IDS:
        try:
            html = fetch_html(f"{BASE_URL}/category/{cid}/")
        except requests.RequestException as e:
            print(f"[warn] カテゴリページ取得失敗: category/{cid} ({e})")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="/item/"]'):
            href = a.get("href", "")
            if "/item/" in href:
                urls.add(href.split("?")[0])
        time.sleep(CRAWL_DELAY_SECONDS)
    return sorted(urls)


def parse_item(url: str) -> dict | None:
    html = fetch_html(url)
    m = JSONLD_PATTERN.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    name = re.sub(r"\s+", " ", (data.get("name") or "")).strip()
    if not name:
        return None

    offers = data.get("offers") or {}
    price = None
    if offers.get("price") is not None:
        price = int(float(offers["price"]))
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability

    return {
        "title": name,
        "price": price,
        "url": url,
        "structural_out_of_stock": structural_out_of_stock,
    }


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_PATTERN.sub("", item["title"])
        base_name = re.sub(r"[　\s]+", " ", base_name).strip()
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = WEIGHT_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
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

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = collect_item_urls()

    all_items = []
    for url in item_urls:
        try:
            item = parse_item(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if item:
            all_items.append(item)
        time.sleep(CRAWL_DELAY_SECONDS)

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
    with open("data_ashcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ashcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
