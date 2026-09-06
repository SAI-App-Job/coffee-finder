# -*- coding: utf-8 -*-
"""
scrape_bean.py

アクティブビーンズ(bean.shop-pro.jp、新潟県新潟市秋葉区荻野町9-14、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【挽き方違いの重複について】
実データ確認済み: 全8件が4銘柄×(豆のまま／挽豆)の2パターンで構成されて
いる。商品名は「(銘柄名)400g<br><font color="red">（豆のまま／挽豆）
送料込み</font></br>」の形式で、挽き方部分を除いた基準名でグルーピング
し、「豆のまま」を優先して代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "アクティブビーンズ",
    "url": "http://bean.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "新潟県新潟市秋葉区荻野町9-14",
    "prefecture": "新潟県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://bean.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
GRIND_TAG_PATTERN = re.compile(r"</?br\s*/?>|<font[^>]*>|</font>")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def fetch_raw_records() -> list[dict]:
    records = []
    for product_url in fetch_pid_urls():
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        script_text = ""
        for script in soup.find_all("script"):
            text = script.string or script.get_text() or ""
            if "var Colorme" in text:
                script_text = text
                break
        m = COLORME_PATTERN.search(script_text)
        if not m:
            continue
        data = json.loads(m.group(1))
        product = data.get("product") or {}
        raw_name = product.get("name") or ""
        if not raw_name:
            continue
        price = product.get("sales_price_including_tax") or product.get("sales_price")
        structural_out_of_stock = product.get("stock_num") == 0
        records.append({
            "raw_name": raw_name,
            "price": int(price) if price is not None else None,
            "url": product_url,
            "structural_out_of_stock": structural_out_of_stock,
        })
    return records


def pick_canonical_records(records: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for rec in records:
        is_whole_bean = "豆のまま" in rec["raw_name"]
        base_name = GRIND_TAG_PATTERN.sub(" ", rec["raw_name"])
        base_name = re.sub(r"（(豆のまま|挽豆)）送料込み", "", base_name)
        base_name = re.sub(r"[\s　]+", " ", base_name).strip()

        existing = by_base_name.get(base_name)
        if existing is None or (is_whole_bean and "豆のまま" not in existing["raw_name"]):
            by_base_name[base_name] = {**rec, "clean_name": base_name}
    return list(by_base_name.values())


def build_record(rec: dict) -> dict | None:
    title = rec["clean_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": rec["price"],
            "product_url": rec["url"],
        }

    stock_status = detect_stock_status(title, rec["structural_out_of_stock"])
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
        "price": rec["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": rec["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    raw_records = fetch_raw_records()
    canonical_records = pick_canonical_records(raw_records)

    records = []
    flavored_records = []
    for rec in canonical_records:
        detail = build_record(rec)
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
    with open("data_bean.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bean.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
