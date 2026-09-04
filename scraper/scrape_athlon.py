# -*- coding: utf-8 -*-
"""
scrape_athlon.py

アスロンコーヒー焙煎所(athloncoffee.ocnk.net、埼玉県飯能市名栗、
自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃのこネット
(Ocnk)クリーンURLテーマ(アダチコーヒーと同系統だが、価格は個別
セレクトオプションではなくOGPタグ`product:price:amount`で取得できる
シンプルな構造)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみ個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに列挙された`/product/N`形式のURL
(36件)を起点とする。

【重量違い・ドリップバッグの重複について】
実データ確認済み: 「西川ブレンド」「名栗ブレンド」「手紙ブレンド」の
3ブレンドと「グアテマラ」「ブラジル カルモデミナス」「コロンビア
スウィートベリー SUP」「インドネシア マンデリン」「タンザニア AA」
「ブラジル カフェインレス 液体CO2処理」の6ストレートが、それぞれ
「100g」「200g」「ドリップバッグ 10g×5個」「ドリップバッグ
10g×10個」の4形態で個別商品登録されている(計36件)。ドリップバッグは
NON_BEAN_KEYWORDSで除外し、残る100g/200gの2形態から最小重量(100g)を
代表として採用する(全9銘柄)。

【価格・重量の取得方法について】
実データ確認済み: 商品名に重量が明記され(例:「西川ブレンド（100ｇ）」)、
価格はOGPメタタグ(`product:price:amount`、税込)から取得できる。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "アスロンコーヒー焙煎所",
    "url": "https://athloncoffee.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "埼玉県飯能市名栗",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://athloncoffee.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*[（(]\s*\d+\s*[gｇ]\s*[）)]\s*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if re.search(r"/product/\d+$", text):
            urls.append(text)
    return urls


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one("title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True).split(" - ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


WHITESPACE_PATTERN = re.compile(r"[\s　]+")


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = TRAILING_WEIGHT_PATTERN.sub("", item["title"]).strip()
        # 理由: 同一銘柄の重量違い商品間で、全角/半角スペースの混在等
        # 表記ゆれ(例:「グアテマラ　【中深煎り】」と「グアテマラ　 【中深煎り】」、
        # 後者は全角+半角の連続スペース)があり、単純なtrailing weight除去だけでは
        # 別の基準名として扱われ重複排除に失敗することを実データで確認済み。
        # 内部の連続空白を単一の半角スペースに正規化してから基準名として使う。
        base_name = WHITESPACE_PATTERN.sub(" ", base_name).strip()
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
        if not fields or any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({"title": fields["title"], "price": fields["price"], "url": product_url})

    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["title"]):
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
    with open("data_athlon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_athlon.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
