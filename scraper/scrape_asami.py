# -*- coding: utf-8 -*-
"""
scrape_asami.py

自家焙煎あさみ珈琲豆店(asami-coffee.ocnk.net、埼玉県本庄市児玉町、
「本庄市唯一の自家焙煎珈琲豆店」を謳う)の商品情報を取得する。
おちゃのこネット(Ocnk)クリーンURLテーマ(アスロンコーヒー焙煎所と
同系統)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみ個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに列挙された`/product/N`形式のURL
(82件)を起点とする。

【非コーヒー豆商品の除外について】
実データ確認済み(82件): 「コーヒー麻袋バック」「コーヒー麻袋
ショルダーバック」「コーヒー麻袋トートバッグ」(複数の同一名重複含む、
豆の梱包用麻袋そのものを商品化したグッズ)・「水だしアイスパック」・
「秩父源流水」(ボトル水)・「ドリップコーヒー」各種・「(深煎り珈琲)
セット」等の詰め合わせ・「中古珈琲焙煎機」・「珈琲豆チョコ」が
コーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。詰め合わせ
セット・送料無料系の福袋商品は例外なく商品名に「送料無料」を含む
ため、これも除外キーワードとして扱う。

【重量違い・重複出品の重複について】
実データ確認済み: 同一銘柄が「200g」「500g（10%OFF）」等の重量違いで
複数登録されているほか、一部商品(CAFE.03・まろやかブレンド・
オリジナルブレンド等)は全く同じ商品名で複数回重複出品されている。
商品名から末尾の重量表記(割引率の注記含む)を取り除いた基準名で
グルーピングし、最小重量を代表として採用する(結果として完全重複も
自然に1件へ統合される)。割引表記の英字が全角(「10%ｏｆｆ」等)で
入力されている商品があるため、判定処理の前にNFKC正規化で全角英数字を
半角に統一する。

【価格・重量の取得方法について】
実データ確認済み: 商品名に重量が明記され、価格はOGPメタタグ
(`product:price:amount`、税込)から取得できる。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "あさみ珈琲豆店",
    "url": "https://asami-coffee.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "埼玉県本庄市児玉町児玉335-15",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://asami-coffee.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "麻袋", "バック", "トートバッグ", "水だし", "源流水",
    "ドリップコーヒー", "セット", "焙煎機", "チョコ", "送料無料",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 理由はモジュールdocstring参照。重量表記の位置(焙煎度カッコの前/後)が
# 商品によって一定しないため、末尾だけでなく文字列中のどこにあっても
# 重量トークン・割引表記(離れた位置にあってもよい)をそれぞれ独立に
# 取り除いてから基準名として使う(単純な末尾一致では
# 「ブルーマウンテンNo.1ブレンド200ｇ【中煎り】」と「...500ｇ【中煎り】
# 10%ｏｆｆ」のような重量前置・割引後置パターンを重複排除できなかった)。
WEIGHT_TOKEN_PATTERN = re.compile(r"\d+\s*[gｇ]")
DISCOUNT_PATTERN = re.compile(r"[（(]?\s*\d+\s*[%％]\s*[Oo][Ff][Ff]\s*[）)]?")
WHITESPACE_PATTERN = re.compile(r"[\s　]+")


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
    raw_title = title_el.get_text(strip=True).split(" - ")[0].strip()
    # 理由: 「10%ｏｆｆ」のように割引表記の英字が全角(ｏｆｆ)で入力されて
    # いる商品があり、半角のO/Fしか見ないDISCOUNT_PATTERNでは検出できず
    # 重複排除に失敗することを実データで確認済み(ブルーマウンテンNo.1
    # ブレンド)。NFKC正規化で全角英数字・％記号等を半角に統一してから
    # 以降の処理に使う。
    title = unicodedata.normalize("NFKC", raw_title)
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_TOKEN_PATTERN.sub("", item["title"])
        base_name = DISCOUNT_PATTERN.sub("", base_name)
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
    with open("data_asami.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_asami.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
