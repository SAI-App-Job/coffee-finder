# -*- coding: utf-8 -*-
"""
scrape_niwacafe.py

庭cafe焙煎所(niwacafe.farmgarden.co.jp、茨城県下妻市下妻乙、
ファームガーデン株式会社が運営する自家焙煎豆のオンライン販売)の
商品情報を取得する。BASE(白ラベルドメイン)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全9件): 「[ギフトセット]」を含む3件(ドリップバッグ
20個セット・オススメコーヒー豆100g×3袋セット・180g×2袋セット)が
複数銘柄の詰め合わせでコーヒー豆単品ではないためNON_BEAN_KEYWORDSで
除外する。残り6件はストレート豆単品(180g固定、重量バリエーション無し)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "庭cafe焙煎所",
    "url": "https://niwacafe.farmgarden.co.jp/",
    "platform": "BASE",
    "address": "茨城県下妻市下妻乙908-1",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://niwacafe.farmgarden.co.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフトセット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


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


def build_record(product_url: str, fields: dict) -> dict | None:
    title = fields["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": fields["price"],
            "product_url": product_url,
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
        "price": fields["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    fields = extract_og_fields(fetch_page(url))
    if not fields:
        return None
    return build_record(url, fields)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue
        if any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record(product_url, fields)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        import json
        with open("data_niwacafe.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_niwacafe.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
