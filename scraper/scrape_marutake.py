# -*- coding: utf-8 -*-
"""
scrape_marutake.py

MARUTAKE COFFEE BEANS(marutake-coffee.com、東京都中野区野方)の商品情報を
取得する。実店舗サイト(marutake-coffee.com、WordPress)自体には店舗案内の
みでオンラインショップ機能が無く、実際の通販はグループ会社のBASE(白ラベル
ドメイン「.official.ec」)のショップ(marutakecb.official.ec)で行われている
ことを実データ確認済み(2026-09時点。マンデリンあのころ/たまじ珈琲と同様の
「情報サイトと通販サイトが別ドメイン」パターン)。

robots.txt確認済み(2026-09時点): marutakecb.official.ecはNAGI COFFEE等と
同一の記述(curl/python-requests/aiohttp等の一般的なHTTPクライアントは
個別にDisallow: /指定があるが、User-agent: *ルールでは/cart/・/web_cart/・
/shops/・/api/shops/・違反報告ページ以外はAllow: /)。

【対象カテゴリと集計ページネーションについて】
実データ確認済み: 「スペシャルティ（シングルオリジン）」(4335050)・
「プレミアム」(4335053)・「スペシャルティブレンド」(4335056)・「デカフェ」
(4514544)・「限定プレミアム＆スペシャルティ」(4515816)の5カテゴリの和集合
(63件)が実際にコーヒー豆単品を指す商品。「Grade」「Country」「Taste」配下の
国別・味わい別カテゴリはすべて上記5カテゴリの商品を横断的に再分類した重複
ビューであることを確認済みのため対象外とする。「ドリップパック」・
「アイスコーヒー」・「Gift」・「限定プレミアム＆スペシャルティ」内の
ギフト商品(実データ確認は本文の除外キーワード参照)も対象外。
【重要】本サイトは新しいJS駆動の無限スクロールテーマを採用しており、
カテゴリページの初回アクセス(/categories/<ID>)には最初のバッチ(24件程度)
しか含まれない。/categories/<ID>/<N>という連番URLでNを増やしていくと
サーバー側でN番目までの累積件数がレンダリングされ、それ以上増えなくなった
時点(前ページと同じ件数)が全件数であることを実データ確認済み(実データでは
N=4で51件から頭打ちを確認)。そのためscrape_category_list()は件数が
増えなくなるまでページ番号を1から増やし続ける。

【商品詳細ページの説明文(【ラベル】値形式)について】
実データ確認済み(63件中複数件で確認): JSON-LDのdescriptionに以下の
「【ラベル】値」形式の行が並ぶ。ストレートは
  【商品名】<豆の名称>
  【生産国】<国名>
  【生産地域】<地域>
  【生産処理】<水洗処理場名等>
  【代表者】<生産者名>
  【標高】<標高>
  【品種】<品種>
  【精製方法】<精選方法>
  【焙煎度】<粗い焙煎度(浅煎り/中煎り等)>
  【内容量】<重量>
ブレンドは【名称】(【商品名】ではない)で始まり、【生産国】が「ウガンダ＋
コロンビア」のように「＋」区切りで複数国を持つ(【生産地域】【標高】
【品種】【精製方法】は無い)。この「＋」区切りの件数でブレンド判定を行う
(たまじ珈琲のカンマ区切りと同じ発想)。

【重量について】
実データ確認済み: 「※ 生豆時の重量で販売しています。焙煎後の豆量は約
10～20%減少します。」という注記があり、焙煎後の正確な重量は不明瞭な幅の
概算のみ(たまじ珈琲と同じ状況)。そのため不確かな計算値を作らず、
【内容量】に明記された表示重量(100g)をそのままweight_gに採用する。

【焙煎度について】
【焙煎度】の値は「浅煎り」「中煎り」等の粗い3〜4段階表記でプロ向け8段階
表記と粒度が異なるため、roast_hintとして保持しroast_levelには反映しない。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "MARUTAKE COFFEE BEANS",
    "url": "https://marutakecb.official.ec/",
    "platform": "BASE",
    "address": "東京都中野区野方6-18-14",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE等と同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://marutakecb.official.ec"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(コーヒー豆単品を指す5カテゴリの和集合)
LIST_CATEGORIES = {
    "4335050": "スペシャルティ（シングルオリジン）",
    "4335053": "プレミアム",
    "4335056": "スペシャルティブレンド",
    "4514544": "デカフェ",
    "4515816": "限定プレミアム＆スペシャルティ",
}

DETAIL_LABEL_PATTERN = re.compile(r"^【(.+?)】\s*(.*)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~－]\s*([\d,]+)\s*[mｍ]")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*[mｍ]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_description_fields(description: str) -> dict:
    """理由はモジュールdocstring参照(【ラベル】値の行を汎用抽出)。"""
    fields: dict[str, str] = {}
    for line in (description or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = DETAIL_LABEL_PATTERN.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def parse_altitude(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    normalized = text.replace(",", "")
    m = ALTITUDE_RANGE_PATTERN.search(normalized)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = ALTITUDE_SINGLE_PATTERN.search(normalized)
    if m:
        value = int(m.group(1))
        return value, value
    return None, None


def parse_weight(text: str | None) -> int | None:
    if not text:
        return None
    m = WEIGHT_PATTERN.search(text)
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict, category_hint: str) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or [{}]
        offer = offers[0] if isinstance(offers, list) else offers
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(offer.get("lowPrice") or offer.get("price") or 0) or None,
            "product_url": product_url,
        }

    fields = parse_description_fields(product.get("description") or "")

    origin_raw = fields.get("生産国")
    origin_values = [p.strip() for p in re.split(r"[＋+、,]", origin_raw or "") if p.strip()]
    # 【生産国】が2件以上ならブレンド、1件なら単一原産地。フィールド自体が
    # 無い場合のみ商品名解析(parse_product)の「ブレンド」判定にフォールバック
    # する(たまじ珈琲と同じ方針。理由はモジュールdocstring参照)
    if len(origin_values) >= 2:
        is_blend = True
    elif len(origin_values) == 1:
        is_blend = False
    else:
        is_blend = parsed["category"] == "ブレンド"
    parsed["category"] = "ブレンド" if is_blend else "ストレート"

    blend_components = []
    origin_country, origin_source = None, None
    processing_method = None
    region_detail = None
    variety = None
    farm_name = None
    producer_name = None
    altitude_min, altitude_max = None, None

    if is_blend:
        for value in origin_values:
            country = detect_country_name(value)
            blend_components.append({"origin_country": country or value, "percentage": None})
    else:
        if origin_values:
            country = detect_country_name(origin_values[0])
            if country:
                origin_country, origin_source = country, "product_description"
        if not origin_country:
            origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

        processing_raw = fields.get("精製方法")
        if processing_raw:
            processing_method = normalize_processing_method(processing_raw)

        region_detail = fields.get("生産地域")
        variety = fields.get("品種")
        farm_name = fields.get("生産処理")
        producer_name = fields.get("代表者")
        altitude_min, altitude_max = parse_altitude(fields.get("標高"))

    parsed = apply_category_hint_fallback(parsed, category_hint)

    offers = product.get("offers") or [{}]
    offer = offers[0] if isinstance(offers, list) else offers
    price = None
    if offer.get("lowPrice") is not None:
        price = int(offer["lowPrice"])
    elif offer.get("price") is not None:
        price = int(offer["price"])
    availability = offer.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": origin_country,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": fields.get("焙煎度"),
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": region_detail,
        "variety": variety,
        "farm_name": farm_name,
        "producer_name": producer_name,
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "blend_components": blend_components,
        "price": price,
        "weight_g": parse_weight(fields.get("内容量")),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    """理由はモジュールdocstring参照(件数が増えなくなるまでページ番号を
    増やし続ける、無限スクロールテーマのSSRページネーション)。"""
    prev_count = -1
    page = 1
    items: dict[str, str] = {}
    while True:
        soup = fetch_page(f"{BASE_URL}/categories/{cid}/{page}")
        found: dict[str, str] = {}
        for link_el in soup.select('a[href*="/items/"]'):
            title_el = link_el.select_one('[class*="itemTitleText"], [class*="title"]')
            href = link_el.get("href", "")
            if not href or "/items/" not in href:
                continue
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            found[product_url] = title_el.get_text(strip=True) if title_el else ""
        items.update(found)
        if len(items) == prev_count:
            break
        prev_count = len(items)
        page += 1
        if page > 15:  # 安全弁(想定外の無限ループ防止)
            break
        time.sleep(CRAWL_DELAY_SECONDS)
    return [{"raw_name": name, "product_url": url} for url, name in items.items()]


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_marutake.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_marutake.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
