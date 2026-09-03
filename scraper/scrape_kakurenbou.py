# -*- coding: utf-8 -*-
"""
scrape_kakurenbou.py

隠房(かくれんぼう、kakurenbou.jp、東京都練馬区練馬)の商品情報を取得する。
実店舗サイト(kakurenbou.jp)自体には店舗案内のみでオンラインショップ機能が無く、
実際の通販はBASEの白ラベルドメイン「.theshop.jp」のショップ
(kakurenbou.theshop.jp)で行われていることを実データ確認済み(2026-09時点。
MARUTAKE COFFEE BEANSの「.official.ec」と同種の白ラベルドメインパターン)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・MARUTAKE COFFEE BEANS等と同一の
記述(curl/python-requests等の一般的なHTTPクライアントは個別にDisallow: /
指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・/api/shops/・
違反報告ページ以外はAllow: /)。本スクレイパーは識別可能な独自User-Agentを
使用するため該当しない。

【住所について】
kakurenbou.jp/shop.htmlの所在地欄はHTMLコメント(<!-- -->)内に隠れているが、
Googleマップの店舗情報(★4.4、63件の口コミ)・Yahoo!マップ・食べログ・ぐるなび
等の複数の独立情報源で「東京都練馬区練馬4-20-3 ミヤマビル」との一致を確認済み
(2026-09時点、豊島園駅から徒歩3分)。コメントアウトされているのは表示上の
都合と考えられ、情報自体は現行と一致するため採用する。

【対象カテゴリについて】
sitemap.xmlで確認できる全8商品は4カテゴリに分かれる。
「ブレンド単品（4種類）」(180154)の4件のみがコーヒー豆単品(重量固定・
産地固定のブレンド)を指す。以下は対象外:
  - 「ブレンド定期便（6ヶ月）」(180153、1件): 定期購入(サブスクリプション)
  - 「ドリップバッグ」(180155、2件): 粉のドリップバッグで豆売りではない
  - 「期間限定商品」(1614430、1件、item 60050776
    「厳選ストレート（月替り）100g×2種」): 実データ確認済み、商品説明を見ると
    「豆の種類（１）：ケニア、カラツAA100g」「豆の種類（２）：エチオピア、
    イルガチェフェのウォテ100g」という、産地の異なる2種類の豆を1つのSKUとして
    バンドル販売する商品(A FEW WORDS COFFEEの「セレクト2種」と同種のアソート
    商品)であり、特定の一豆を指さないため対象外。

【商品説明文について】
実データ確認済み(4件全件): 「豆の種類：《コスタリカ/エチオピア他》」のように
「他」を含む曖昧な表記で、配合国が2〜3ヶ国程度あることは分かるが正確な内訳が
わからない(構造化された配合比率の記載も無い)。そのためblend_componentsは
未対応とし、origin_countryもNoneのままにする(たまじ珈琲・MARUTAKE COFFEE
BEANSとは異なり「他」で打ち切られる表記のため、既存の「、」区切りカウント
方式は適用できない)。全4件とも商品名(「◯◯ブレンド」等)または本カテゴリ
自体からブレンドと判定できる。ロースト度合は商品名に「シティ」「フルシティ」
等プロ向け8段階表記(ROAST_KEYWORDS)がそのまま含まれているため、
parse_product()のroast_level判定にそのまま乗せられる。

【重量・価格・在庫について】
実データ確認済み: 全4件とも商品名末尾に「200g」を含む固定重量(バリエーション
無し)。JSON-LD(schema.org Product)のoffersにprice・availability
(http://schema.org/InStock 等)が構造化されている(MARUTAKE COFFEE BEANSと
同じBASE標準テンプレート)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "隠房",
    "url": "https://kakurenbou.theshop.jp/",
    "platform": "BASE",
    "address": "東京都練馬区練馬4-20-3 ミヤマビル101",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・MARUTAKE COFFEE BEANS等と"
                          "同一の記述。/cart/・/web_cart/・/shops/・/api/shops/・違反報告"
                          "ページ以外はUser-agent: *でAllow。curl/python-requests等は"
                          "個別にDisallow: /指定あり、本スクレイパーは識別可能な"
                          "User-Agentを使用)",
}

BASE_URL = "https://kakurenbou.theshop.jp"
# 理由はモジュールdocstring参照(コーヒー豆単品を指す1カテゴリのみ)
LIST_CATEGORIES = {
    "180154": "ブレンド単品",
}
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_weight_from_title(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict, category_hint: str) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    # 理由はモジュールdocstring参照(説明文が「他」を含む曖昧な配合表記のため
    # blend_components・origin_countryは未対応。全件ブレンドカテゴリ)
    parsed["category"] = "ブレンド"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": None,
        "origin_source": None,
        "designated_brand": None,
        "processing_method": None,
        "grade": None,
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight_from_title(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{cid}")
    results = []
    seen = set()
    for link_el in soup.select('a[href*="/items/"]'):
        href = link_el.get("href", "")
        if "/items/" not in href or href in seen:
            continue
        seen.add(href)
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        # 理由: アンカー自体が画像・タイトル・価格・説明文をまとめて内包しているため、
        # get_text()では全部連結されてしまう。タイトル用の子要素を個別に取る
        # (MARUTAKE COFFEE BEANSと同じ"itemTitleText"を含むクラス名で判定)。
        title_el = link_el.select_one('[class*="itemTitleText"], [class*="title"]')
        title = title_el.get_text(strip=True) if title_el else ""
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> list[dict]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records = scrape_all_products()
        output = {"shop": SHOP_INFO, "products": records}
        with open("data_kakurenbou.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_kakurenbou.json に出力しました")
