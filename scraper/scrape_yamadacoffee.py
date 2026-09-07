# -*- coding: utf-8 -*-
"""
scrape_yamadacoffee.py

山田珈琲(www.yamadacoffee.com、岐阜県岐阜市福光東1-25-3、自家焙煎豆の
オンライン販売)の商品情報を取得する。おちゃのこネット(Ocnk、カスタム
ドメインでプロキシ)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【対象カテゴリの絞り込みについて】
実データ確認済み: カテゴリ一覧は10種類あるが、単一銘柄のコーヒー豆
販売は「際立つ風味を持つコーヒー農園の豆」(product-list/47、シングル
オリジン)・「山田珈琲オリジナル」(product-list/58、オリジナルブレンド)・
「30周年スペシャルブレンド」(product-list/193)・「エスプレッソロースト」
(product-list/194、いずれも現時点では商品0件だが将来の追加に備え含める)
のみ。それ以外(珈琲を楽しむ器具など=器具、コーヒーバッグ=ドリップ
バッグ、リキッド、アイスコーヒーバッグ、有料紙袋=器具、山田珈琲記念
ギフト=詰め合わせ)は単一銘柄の豆売りではないため、CATEGORY_PATHSで
対象カテゴリのみに絞り込む。実データ確認済み: 全29件(47:15件+58:14件)、
非コーヒー豆商品の混在は無く全件が対象。

【重量違いの重複について】
実データ確認済み: 全銘柄が100g/200g/500gの複数サイズで個別商品登録
されている(Ocnkのvariation機構は使わず、重量ごとに別商品ページ)。
商品名の重量表記は全角数字(「５００ｇ」)だが、Pythonの\\dは全角数字も
Unicode十進数字として一致し、int()もそのまま変換できるため追加の
正規化は不要(コーヒー幸房多香・ミーツコーヒー等の全角重量表記と同じ
挙動を実データで確認済み)。商品名末尾の重量を除いた基準名でグルーピング
し、最小重量(100g)を代表として採用する。

【価格について】
実データ確認済み: 商品詳細ページの<meta property="product:price:amount">は
税込価格(例: 3,700円(税別)の商品はcontent="3996")。一覧ページの表示
価格(税込)と一致するため、この税込価格を採用する(pConf.priceは税別の
ため使わない)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "山田珈琲",
    "url": "https://www.yamadacoffee.com/",
    "platform": "おちゃのこネット",
    "address": "岐阜県岐阜市福光東1-25-3",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://www.yamadacoffee.com"
# 「際立つ風味を持つコーヒー農園の豆」(47)はシングルオリジン、それ以外の3カテゴリは
# いずれもブレンド(「山田珈琲オリジナル」「30周年スペシャルブレンド」「エスプレッソ
# ロースト」)。商品名自体には「ブレンド」の語を含まない銘柄(「山田珈琲」「ソレイユ」
# 「スターダスト」「ビターロースト」「エスプレッソロースト」等)が実データで多数
# 確認されたため、parse_product()のキーワード判定だけでは正しくカテゴリ分類できない。
# 他店舗のスクレイパー(scrape_rakuen.py等)と同じ「カテゴリ由来のブレンド判定」の
# house patternに従い、由来カテゴリがブレンド系なら判定を上書きする。
CATEGORY_PATHS = ["product-list/47", "product-list/58", "product-list/193", "product-list/194"]
BLEND_CATEGORY_PATHS = {"product-list/58", "product-list/193", "product-list/194"}
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS: list[str] = []
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> dict[str, bool]:
    """商品URL → 由来カテゴリがブレンド系だったかどうか、のマップを返す。
    同一商品が複数カテゴリに重複掲載されていた場合、一度でもブレンド系
    カテゴリ経由で見つかっていればブレンド扱いとする。"""
    url_is_blend: dict[str, bool] = {}
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        is_blend_category = path in BLEND_CATEGORY_PATHS
        for a in soup.select(f'a[href*="{BASE_URL}/product/"]'):
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if not m:
                continue
            url = f"{BASE_URL}/product/{m.group(1)}"
            url_is_blend[url] = url_is_blend.get(url, False) or is_blend_category
    return url_is_blend


def extract_fields(soup: BeautifulSoup, product_url: str, category_is_blend: bool) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price, "url": product_url, "category_is_blend": category_is_blend}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_PATTERN.sub("", item["title"]).strip()
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
    if item.get("category_is_blend") and parsed["category"] != "フレーバー":
        parsed["category"] = "ブレンド"

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
    url_is_blend = fetch_product_urls()

    all_items = []
    for product_url, category_is_blend in url_is_blend.items():
        try:
            fields = extract_fields(fetch_page(product_url), product_url, category_is_blend)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if fields:
            all_items.append(fields)

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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_yamadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamadacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
