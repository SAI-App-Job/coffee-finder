# -*- coding: utf-8 -*-
"""
scrape_tremolo.py

トレモロコーヒーロースター(shop.tremolocoffee.net、埼玉県草加市草加、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(白ラベル
ドメイン)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品名の構造について】
実データ確認済み: 全89件が例外なく「【通信販売:80g】」「【通信販売:
160g】」「【店頭受取:80g】」「【店頭受取:160g】」のいずれかの接頭辞を
持つ。豆単品はこの接頭辞に必ず重量(:80g等)が含まれる一方、グッズ類
(ステンレスタンブラー・キャニスター缶・ドリップバッグセット・
トートバッグ・缶バッジ・マグカップ・エコバッグ・ドリッパー・フィル
ター・水出しアイスコーヒーパック等)は接頭辞に重量を含まない
「【通信販売】」「【店頭受取】」のみの表記であることを確認済み。
そのため接頭辞に":重量g"を含む商品だけを対象とすることで、追加の
NON_BEAN_KEYWORDSを用意せずに豆単品とグッズを機械的に判別できる。

【通信販売/店頭受取・重量違いの重複について】
実データ確認済み: 同一銘柄が「通信販売80g」「通信販売160g」
「店頭受取80g」「店頭受取160g」の4形態で個別商品登録されている
(41銘柄相当)。接頭辞を取り除いた基準名でグルーピングし、「通信販売」
チャンネルの中から最小重量(80g)を代表として採用する(店頭受取専用
在庫等の理由で通信販売側が存在しない銘柄は無いことを実データで確認
済み)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "トレモロコーヒーロースター",
    "url": "https://shop.tremolocoffee.net/",
    "platform": "BASE",
    "address": "埼玉県草加市草加3-8-15",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.tremolocoffee.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PREFIX_PATTERN = re.compile(r"^【(通信販売|店頭受取):(\d+)g】\s*")
WHITESPACE_PATTERN = re.compile(r"[\s　]+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        m = PREFIX_PATTERN.match(item["title"])
        if not m:
            continue
        channel, weight = m.group(1), int(m.group(2))
        base_name = WHITESPACE_PATTERN.sub(" ", PREFIX_PATTERN.sub("", item["title"])).strip()
        item = {**item, "channel": channel, "weight_g": weight, "base_name": base_name}

        existing = by_base_name.get(base_name)
        if existing is None:
            by_base_name[base_name] = item
            continue
        existing_rank = (0 if existing["channel"] == "通信販売" else 1, existing["weight_g"])
        candidate_rank = (0 if channel == "通信販売" else 1, weight)
        if candidate_rank < existing_rank:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
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
    product_urls = fetch_sitemap_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue
        all_items.append({"title": fields["title"], "price": fields["price"], "url": product_url})

    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["base_name"]):
            records.append(prev)
            continue

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
    with open("data_tremolo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tremolo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
