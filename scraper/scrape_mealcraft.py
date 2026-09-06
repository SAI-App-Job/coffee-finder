# -*- coding: utf-8 -*-
"""
scrape_mealcraft.py

自家焙煎珈琲ミールクラフト(MEALCRAFT COFFEE ROASTERS、
mealcraft.jp(mealcraft.ocnk.netのカスタムドメイン)、新潟県十日町市
水口沢45番地、自家焙煎豆のオンライン販売)の商品情報を取得する。
おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【商品一覧の取得方法について】
実データ確認済み: トップページのナビゲーションに焙煎度別
(ふか苦/極苦/爽やか/柔らか/ほろ苦)・産地別(オリジナルブレンド/南米/
中米/アフリカ/アジア)・器具(ペーパードリップ/フレンチプレス/コーヒー
ミル)・その他(輸入菓子/コーヒーギフト/ドリップバッグ/水出しパック/
リキッドコーヒー/お得な1kg袋入)の複数カテゴリが並ぶ。産地別5カテゴリ
+特別限定豆カテゴリの計6カテゴリ(焙煎豆のみ・器具やギフト等を含まない)
のみを巡回し、含まれるproduct/Nリンクを和集合で収集する(焙煎度別
カテゴリは産地別カテゴリと同じ商品の重複掲載のため巡回不要)。

【重量違いの重複について】
実データ確認済み: 全18銘柄が150g/250g/500gの3サイズで個別商品登録
されている。商品名から「(重量袋入)」の部分を除いた基準名で
グルーピングし、最小重量(150g)を代表として採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎珈琲ミールクラフト",
    "url": "https://www.mealcraft.jp/",
    "platform": "おちゃのこネット",
    "address": "新潟県十日町市水口沢45番地",
    "prefecture": "新潟県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://www.mealcraft.jp"
CATEGORY_PATHS = [
    "product-list/81", "product-list/82", "product-list/83",
    "product-list/84", "product-list/85", "product-list/89",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_BAG_PATTERN = re.compile(r"[（(]\s*\d+\s*[gｇ]\s*袋入\s*[）)]")
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
    if not title:
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_BAG_PATTERN.sub("", item["title"]).strip()
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
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append({"title": fields["title"], "price": fields["price"], "url": product_url})

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
    with open("data_mealcraft.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mealcraft.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
