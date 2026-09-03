# -*- coding: utf-8 -*-
"""
scrape_kagurazaka.py

神楽坂珈琲焙煎所(kagurazakacoffee.com、東京都文京区関口、江戸川橋・神楽坂)の
商品情報を取得する。MakeShop(GMOメイクショップ)。このプロジェクトで初対応の
プラットフォーム。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404。EUC-JPの
汎用Apache 404ページが返るのみで、サイト本体はUTF-8。CAFE FACON・Muiの
ShopServeと同種の「robots.txtが無い=実質全面許可」状態)。

【カテゴリ構造について】
実データ確認済み: 商品一覧ページ(/view/category/ctN)には常に「おすすめ
アイテム」という全ページ共通の固定ウィジェット(4件)が別途表示されるため、
これを実際のカテゴリ内商品と誤認しないよう注意が必要(該当カテゴリが空でも
表示される)。実際の商品はsection.category-wrapper > ul.category-item-list
内のa[href*="/view/item/"]のみから取得する。
対象は「オリジナルブレンド」(ct9、定番/季節限定等のサブカテゴリの和集合、
25件)・「世界のストレート豆」(ct18、カリブ海/中南米/アフリカ/アジア・
オセアニアのサブカテゴリの和集合、13件)・「カフェインレス」(ct19、1件)・
「数量限定商品」(ct37、3件、ct18と一部重複するが商品URL単位で自然に
重複排除される)。「コーヒー器具」「ドリップバッグ関連」「グッズ」「アイス
コーヒー」は対象外。

【非コーヒー豆の除外について】
実データ確認済み: ct9内に「神楽坂ブレンド×朝日坂ブレンド200g　焙煎豆
ギフト」(2種のブレンドを詰め合わせたギフト商品、特定の一豆を指さない)・
「手軽でおいしい！ドリップコーヒーバッグ 5個セット」(ドリップバッグ、豆売り
ではない)の2件が混在するため、NON_BEAN_KEYWORDSで除外する。

【重量について】
実データ確認済み: 注文後焙煎モデルで、商品名に「(生豆計り100g)」のように
生豆(焙煎前)の重量が明記されている。焙煎後の正確な重量は開示されていない
(たまじ珈琲・MARUTAKE COFFEE BEANSと同じ状況)ため、不確かな計算値を作らず
商品名に明記された表示重量(100g)をそのままweight_gに採用する。

【価格・在庫について】
商品詳細ページにJSON-LD(schema.org Product)が埋め込まれており、
offers.price・offers.availability(https://schema.org/InStock 等)から
構造化データを取得できる(GONZO CAFE&BEANS等のBASE系列と同様の構造)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "神楽坂珈琲焙煎所",
    "url": "https://www.kagurazakacoffee.com/",
    "platform": "MakeShop",
    "address": "東京都文京区関口1-3-5 ロジビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず"
                          "404。CAFE FACON・Mui等のShopServeと同種の"
                          "「robots.txtが無い=実質全面許可」状態)",
}

BASE_URL = "https://www.kagurazakacoffee.com"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "ct9": "オリジナルブレンド",
    "ct18": "世界のストレート豆",
    "ct19": "カフェインレス",
    "ct37": "数量限定商品",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["焙煎豆ギフト", "ドリップコーヒーバッグ"]
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


def parse_weight_from_title(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict, category_hint: str) -> dict:
    title = (product.get("name") or "").strip()

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        price = int(float(offers["price"])) if offers.get("price") is not None else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    parsed = apply_category_hint_fallback(parsed, category_hint)

    description = product.get("description") or ""
    roast_hint = None
    m = re.search(r"おすすめロースト[：:]\s*([^\s。、]+)", description)
    if m:
        roast_hint = m.group(1)

    offers = product.get("offers") or {}
    price = int(float(offers["price"])) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(店独自の紹介文中の表記のためroast_hintに保持)
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight_from_title(title),
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


def scrape_category_list(ct: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/view/category/{ct}")
    results = []
    seen = set()
    for wrapper in soup.select("section.category-wrapper"):
        for link_el in wrapper.select('a[href*="/view/item/"]'):
            href = link_el.get("href", "")
            if "/view/item/" not in href or href in seen:
                continue
            seen.add(href)
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            title_el = link_el.select_one("span.category-item-name")
            title = title_el.get_text(strip=True) if title_el else ""
            results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for ct, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(ct):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

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
        with open("data_kagurazaka.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_kagurazaka.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
