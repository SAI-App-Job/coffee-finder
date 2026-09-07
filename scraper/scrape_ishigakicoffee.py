# -*- coding: utf-8 -*-
"""
scrape_ishigakicoffee.py

自家焙煎工房 石垣珈琲(ishigaki-coffee.com、静岡県駿東郡清水町、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全58件): ドリップバッグギフト(10g×14/21袋入り、箱詰め)・
自家焙煎煎りたてコーヒーギフト(200g×2/3袋入り、箱詰め)・インスタントコーヒー・
水出しアイスコーヒー(55g×3/5袋入り)が非対象。NON_BEAN_KEYWORDSで除外する。
「苺珈琲」「薔薇珈琲」「キャラメルコーヒー」は商品名に(フレーバーコーヒー)と
明記されており、coffee_parser側のフレーバー判定で自動的に別枠(フレーバー
コーヒー)に分離される。「★自家焙煎のアイスコーヒー（深炒り）200ｇ★」は
水出し(リキッド)ではなく通常の焙煎豆(200g)として販売されているため対象に含める。

【重量違いの重複について】
実データ確認済み: モカマタリ・ブラジル・コロンビア・スプレモ・ホンジュラス・
マンデリン・クリスタルマウンテンの6銘柄が180g(通常)/200g(一部)の2サイズで
別商品登録されている。
商品名末尾の「｜自家焙煎工房　石垣珈琲」等の店名部分と重量表記(【や(の
全角/半角ゆれを含む)を除いた基準名でグルーピングし、最小重量(180g)を
代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "石垣珈琲",
    "url": "https://ishigaki-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "静岡県駿東郡清水町新宿7-1",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://ishigaki-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグギフト", "コーヒーギフト", "インスタントコーヒー", "水出しアイスコーヒー",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_PAREN_STRIP_PATTERN = re.compile(r"[（(]\s*\d+\s*[gｇ]\s*[）)]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def fetch_raw_product(soup: BeautifulSoup) -> dict | None:
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
    return data.get("product") or {}


def canonical_base_name(title: str) -> str:
    base_name = WEIGHT_PAREN_STRIP_PATTERN.sub("", title)
    base_name = re.sub(r"[|｜]", " ", base_name)
    base_name = re.sub(r"[　\s]+", " ", base_name).strip()
    return base_name


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = canonical_base_name(item["title"])
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

    structural_out_of_stock = item.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
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
    product_urls = fetch_pid_urls()

    all_items = []
    for product_url in product_urls:
        try:
            product = fetch_raw_product(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not product:
            continue
        title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = product.get("sales_price_including_tax") or product.get("sales_price")
        all_items.append({
            "title": title,
            "price": int(price) if price is not None else None,
            "url": product_url,
            "stock_num": product.get("stock_num"),
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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_ishigakicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ishigakicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
