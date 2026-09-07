# -*- coding: utf-8 -*-
"""
scrape_pandacoffee.py

パンダコーヒーロースターズ(pandacoffee.ocnk.net、愛知県名古屋市北区
若鶴町235 パークサイド小川1F、自家焙煎豆のオンライン販売)の商品情報を
取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【商品一覧の取得方法について】
実データ確認済み: 本店は「品種で選ぶ」「精製法で選ぶ」「産地(地域)で
選ぶ」等、同一商品に何十ものタグ付きカテゴリ(product-group/3〜72)が
横断的に付与されており、和集合を取ろうとすると70件以上のページ巡回が
必要になる。実データ確認の結果、「ローストで選ぶ：フレンチロースト/
深煎り」(product-group/30)と「ローストで選ぶ：シティロースト/やや
深煎り」(product-group/31)の2カテゴリだけで、焙煎豆単品(ストレート+
オリジナルブレンド)全21件を過不足なく網羅できることを確認済み
(当店で使われている焙煎度はこの2種類のみで、ドリップバッグ・生豆・
コーヒー器具・定期購入・詰め合わせセット等は焙煎度カテゴリに属さない
ため自然に除外される)。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記2カテゴリには非対象商品は含まれない
(確認済み、生豆・器具・ドリップバッグ・セット・定期購入は別カテゴリ)。

【重量・価格の取得について】
実データ確認済み: 大半の商品名に重量(200g)が明記されており、価格は
product:price:amount のOGPメタタグにそのまま入っている(重量バリエー
ションなし、挽き方バリアントのみで価格は同一)。一部商品(コスタリカ
サンタテレサ2000等)は商品名に重量が無いが、価格帯が200g商品と同水準
であることを確認済みのためweight_gはNoneのまま許容する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "パンダコーヒーロースターズ",
    "url": "https://pandacoffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "愛知県名古屋市北区若鶴町235 パークサイド小川1F",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://pandacoffee.ocnk.net"
CATEGORY_PATHS = ["product-group/30", "product-group/31"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    pids: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select(f'a[href*="{BASE_URL}/product/"]'):
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if m:
                pids.add(m.group(1))
    return [f"{BASE_URL}/product/{pid}" for pid in pids]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


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
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue

        detail = build_record({**fields, "url": product_url})
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
    with open("data_pandacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pandacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
