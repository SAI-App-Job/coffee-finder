# -*- coding: utf-8 -*-
"""
scrape_sakaicoffee.py

さかい珈琲店(katch.ne.jp/~sakai-coffee/が情報サイト、実際の通販は
sakaicoffee.shop-pro.jp、愛知県刈谷市大正町7-103、自家焙煎豆のオンライン
販売)の商品情報を取得する。カラーミーショップ(Shop-Pro)。楽天/Yahoo!
ショッピングにも出店しているが、モール側は対象外とし自社shop-pro.jp店舗
のみを対象とする。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【重量違いの重複について】
実データ確認済み(全163件): 主力銘柄が200g/300g/400g/500g/1kgの最大5
サイズで個別商品登録されている(一部は200g〜500gのみ、または200g単品の
福袋等)。商品名から重量表記と末尾の注記(「（○○から変更しました）」
「（しんざん）」等の読み仮名・変更履歴の丸括弧書き。同一銘柄の全サイズで
共通のため取り除いても支障ない)を除いた基準名でグルーピングし、最小重量
(200g、一部300g)を代表として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「深煎り/中煎り/中深煎り コーヒー豆飲み比べセット」
(2銘柄の詰め合わせ、各種の組み合わせで約40件)・「【お試し】○○飲み比べ
セット」(同上)・「カップオンコーヒー【大正ブレンド】10袋」(個包装
ドリップ形態)・「「黄色い自転車」珈琲豆屋のひさこのエッセイ」(店主の
エッセイ本、コーヒー豆ではない)が非対象。NON_BEAN_KEYWORDSで除外する。
残り約116件(重複除去後24銘柄)を対象とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "さかい珈琲店",
    "url": "https://sakaicoffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛知県刈谷市大正町7-103",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://sakaicoffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["飲み比べセット", "カップオンコーヒー", "のエッセイ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"([\d０-９]+)\s*[gｇ]")
WEIGHT_KG_PATTERN = re.compile(r"([\d０-９]+)\s*[kKｋＫ][gｇ]")
PAREN_PATTERN = re.compile(r"[（(][^）)]*[）)]")
WHITESPACE_PATTERN = re.compile(r"\s+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def weight_from_title(title: str) -> int | None:
    km = WEIGHT_KG_PATTERN.search(title)
    if km:
        return int(km.group(1)) * 1000
    gm = WEIGHT_PATTERN.search(title)
    return int(gm.group(1)) if gm else None


def base_name_key(title: str) -> str:
    """理由はモジュールdocstring参照(重量表記と読み仮名/変更履歴の丸括弧
    書きを除いた基準名でグルーピングする)。"""
    name = WEIGHT_KG_PATTERN.sub("", title)
    name = WEIGHT_PATTERN.sub("", name)
    name = PAREN_PATTERN.sub("", name)
    return WHITESPACE_PATTERN.sub("", name)


def extract_item(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    return {
        "title": title,
        "price": int(price) if price is not None else None,
        "url": product_url,
        "stock_num": product.get("stock_num"),
    }


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        key = base_name_key(item["title"])
        weight_key = weight_from_title(item["title"]) or float("inf")
        existing = by_base_name.get(key)
        existing_weight = weight_from_title(existing["title"]) if existing else None
        existing_weight = existing_weight if existing_weight is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[key] = item
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

    structural_out_of_stock = item.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_g = weight_from_title(title)

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
    product_urls = fetch_pid_urls()

    all_items = []
    for product_url in product_urls:
        try:
            item = extract_item(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if item is None:
            continue
        all_items.append(item)

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_sakaicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sakaicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
