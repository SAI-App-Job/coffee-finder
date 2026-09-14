# -*- coding: utf-8 -*-
"""
scrape_tsunagucoffee.py

つなぐ珈琲(ponkotsudrip.base.shop、秋田県大仙市南外上野189-24、自家焙煎豆
のオンライン販売)の商品情報を取得する。BASE。店主は「秋田県大仙市の限界
集落の片隅で、ひっそりと手網焙煎」「秋田市のどこかで、出店営業で不定期」
と自称しており実店舗を持たない小規模個人焙煎者だが、特定商取引法ページに
記載された住所は上記(登録上の所在地)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
特定商取引法ページ(https://ponkotsudrip.base.shop/law)で実データ確認済み
(2026-09時点): 「所在地」欄に「大仙市南外上野189-24」との記載を確認。
候補リストの住所と一致。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【対象商品について】
実データ確認済み(sitemap.xml全32件): 水出しコーヒー・ビスコッティ・
ドリップバッグ/ドリップバック(単品・詰め合わせ・定期便とも)・複数銘柄の
飲み比べセット・「店主の気まぐれ」を冠する福袋的商品・「焙煎士を1年
見守る」支援型サブスクリプション・期間限定フレーバー豆の「コース」商品
などが多数を占め、NON_BEAN_KEYWORDSで除外する。残るのは単一銘柄の
コーヒー豆(アイスブレンド・エチオピア・ブラジル・マンデリン・キリマン
ジャロ・中国雲南プーアル)で、いずれも100g/200gの重量違いが個別商品登録
されている(1件のみ100g単品)。重量違いの重複は基準名でグルーピングし、
最小重量を代表として採用する(298coffeeと同じ方式)。ただし「ブラジル完熟
手摘中深200g」と「ブラジル完熟手摘 中深煎 100g」は表記ゆれ(スペース・
「煎」の有無)により基準名が一致せず、実データ確認の結果2件とも別商品として
扱われる(店舗側の表記自体が不統一なため)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "つなぐ珈琲",
    "url": "https://ponkotsudrip.base.shop/",
    "platform": "BASE",
    "address": "秋田県大仙市南外上野189-24",
    "prefecture": "秋田県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://ponkotsudrip.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "水出し", "セット", "ビスコッティ", "ドリップバッグ", "ドリップバック",
    "定期便", "飲み比べ", "気まぐれ", "見守る", "コース",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


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
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({"title": title, "price": fields["price"], "url": product_url})

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
    with open("data_tsunagucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tsunagucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
