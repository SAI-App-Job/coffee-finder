# -*- coding: utf-8 -*-
"""
scrape_classico.py

Classico(classico-onlineshop.jp、広島県尾道市土堂1-3-28、自家焙煎豆の
オンライン販売)の商品情報を取得する。プラットフォーム: 独自ECシステム
(EC-CUBE系と思われる/product/<id>・/product-list/<category_id>形式の
URL構造。BASE/Shopify/カラーミー/Ocnk/theShop/EC Force等のいずれにも
該当しない)。

【運営会社について】
特定商取引法ページ(https://www.classico-onlineshop.jp/info)で実データ
確認したところ、運営会社は「株式会社瀬戸内コーヒー焙煎所 Classico
（クラシコ）」、住所は候補リストと一致する「広島県尾道市土堂1-3-28」
であることを確認した(2026-09時点)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみDisallow: /、それ以外(本スクレイパーのUser-Agentを
含む)は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xml(https://www.classico-onlineshop.jp/
sitemap.xml)に/product/<id>形式の商品詳細ページへのリンクが21件含まれて
おり、これを商品URL一覧として利用する。一覧ページ(/product-list/<id>)には
リキッド・アイスコーヒー(カテゴリ49、瓶入り完成品でコーヒー豆単品では
ない)、ペルー・ホンジュラス(カテゴリはあるがsitemap.xml時点で出品0件)の
カテゴリも存在するが、sitemap.xmlに現れる21件の商品詳細ページのみを対象と
すれば十分(実データ確認済み、リキッド・アイスコーヒーはsitemap.xmlに
現れない=非出品中)。

【商品情報の取得方法について】
実データ確認済み: 各商品ページのog:titleメタタグに「銘柄名（重量g）」の
形式で商品名と重量が入っており(例:「深煎りブレンド（300g）」)、価格は
product:price:amountメタタグからそのまま取得できる。在庫状況はページ本文の
「在庫あり」表記の有無で判定する。

【重量違いの重複について】
実データ確認済み: グアテマラ・エチオピア・ブラジル・ケニア・コスタリカ・
深煎りブレンド・インドネシア(マンデリン)の7銘柄がいずれも200g/300g/500gの
3種類の重量で別々の商品ページとして登録されている。og:titleから
「（数字g）」を除いた基準名でグルーピングし、最小重量(200g)を代表として
採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionは「…」で約100文字に切り詰められて
おり使用できない。代わりに商品詳細ページのdiv.detail_desc_box内に、
「ロースト：」「印象：」から始まる全文のテイスティング文+産地スペック
(産地/農園/標高/品種/精製)が入っていることを確認した。末尾に
「焙煎方式：」という見出しから焙煎機の特性説明・保存方法・挽き方の
説明・支払方法等の定型文が続くため、この見出しの直前で打ち切る
(コスタリカのみ「印象：近日掲載」でテイスティング文が未掲載だが、
産地スペックは掲載されているためそのまま採用する)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Classico",
    "url": "https://www.classico-onlineshop.jp/",
    "platform": "独自ECシステム(EC-CUBE系と推定)",
    "address": "広島県尾道市土堂1-3-28",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.classico-onlineshop.jp"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"（(\d+)\s*[gｇ]）")
FLAVOR_STOP_PATTERN = re.compile(r"焙煎方式：")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(SITEMAP_URL)
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = re.sub(r"\s+", " ", title_el["content"].strip())
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    out_of_stock = "在庫あり" not in soup.get_text()

    flavor_notes = None
    desc_el = soup.select_one("div.detail_desc_box")
    if desc_el:
        text = desc_el.get_text("\n", strip=True)
        m = FLAVOR_STOP_PATTERN.search(text)
        if m:
            text = text[:m.start()]
        flavor_notes = text.strip() or None

    return {"title": title, "price": price, "out_of_stock": out_of_stock, "flavor_notes": flavor_notes}


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    m = WEIGHT_PATTERN.search(title)
    weight_g = int(m.group(1)) if m else None
    base = WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item["base_name"] = base
        item["weight_g"] = weight_g
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base] = item
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

    stock_status = detect_stock_status(title, item["out_of_stock"])

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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
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
        all_items.append({
            "title": fields["title"],
            "price": fields["price"],
            "out_of_stock": fields["out_of_stock"],
            "flavor_notes": fields.get("flavor_notes"),
            "url": product_url,
        })

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
    with open("data_classico.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_classico.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
