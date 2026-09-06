# -*- coding: utf-8 -*-
"""
scrape_saikaboo.py

自家焙煎珈琲豆の店「彩香房」(saikaboo.ocnk.net、山梨県北杜市小淵沢町
上笹尾3261-134、有機JAS認証コーヒー豆を中心とした自家焙煎豆のオンライン
販売)の商品情報を取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに個別商品ページへのリンクが含まれて
いないため、商品グループ(product-group/1〜9)と商品リスト
(product-list/10,11,13)の計10ページを巡回し、含まれるproduct/N
リンクを和集合で収集する(まめぽっとと同じ方式)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全27件のうち「商品移行中！」(削除予定の旧商品、
価格情報なし)・「贈答（プレゼント）おまかせパッケージ」(詰め合わせ、
価格情報なし)が非対象。NON_BEAN_KEYWORDSで除外する。残り25件を対象と
する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "彩香房",
    "url": "http://saikaboo.com/",
    "platform": "おちゃのこネット",
    "address": "山梨県北杜市小淵沢町上笹尾3261-134",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://saikaboo.ocnk.net"
CATEGORY_PATHS = [
    "product-group/1", "product-group/2", "product-group/3", "product-group/4",
    "product-group/5", "product-group/8", "product-group/9",
    "product-list/10", "product-list/11", "product-list/13",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["商品移行中", "おまかせパッケージ"]
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
    title_el = soup.find("title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True).split(" - ")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
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
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record({"title": fields["title"], "price": fields["price"], "url": product_url})
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
    with open("data_saikaboo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_saikaboo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
