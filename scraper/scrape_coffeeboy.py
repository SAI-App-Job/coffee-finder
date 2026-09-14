# -*- coding: utf-8 -*-
"""
scrape_coffeeboy.py

徳山コーヒーボーイ(COFFEEBOY、store.coffeeboy.co.jp、山口県下松市平田550番地
の2、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ。

【住所について】
運営会社の公式コーポレートサイト(https://www.coffeeboy.co.jp/aboutus)で
実データ確認済み(2026-09時点): 「所在地　〒744-0021 山口県下松市平田550番地
の2」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。それ以外は制限なし。

【対象カテゴリについて】
実データ確認済み: このショップはカルディコーヒーファーム的な複合物販店で、
コーヒー豆以外にオフィスコーヒー(cbid=..&csid=4、業務用)・マンスリー
ビーンズ(csid=8、定期便)・トライアルセット(csid=5、複数銘柄セット)・
業務用コーヒー(csid=10、卸売)・ギフト企画(csid=20/21)・紅茶等の多数の
非対象カテゴリを持つため、コーヒー豆単品を扱う4カテゴリ(コーヒー豆/COFFEEBOY
ブレンド csid=2、ストレートコーヒー csid=3、スペシャルティコーヒー csid=6、
プレミアムコーヒー csid=7)のみをクロール対象とする(4カテゴリ合算・重複排除で
76商品)。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記4カテゴリ内にも、複数銘柄の詰め合わせ(セット)・
ギフト用の商品が一部混在するため、NON_BEAN_KEYWORDSで除外する。

【重量違いの重複について】
実データ確認済み: 同一銘柄が複数重量(100g/200g/500g等)の個別商品として
登録されている場合があるため、商品名から重量表記を除いた基準名でグルーピング
し、最小重量を代表として採用する(タウンコーヒーと同じ方式)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "COFFEEBOY（徳山コーヒーボーイ）",
    "url": "https://store.coffeeboy.co.jp/",
    "platform": "カラーミーショップ",
    "address": "山口県下松市平田550番地の2",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow、それ以外は制限なし)",
}

BASE_URL = "https://store.coffeeboy.co.jp"
BEAN_CATEGORY_IDS = [2, 3, 6, 7]  # 理由はモジュールdocstring参照
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "セット", "ギフト", "トライアル", "詰め合わせ", "福袋", "アソート",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    urls: set[str] = set()
    for csid in BEAN_CATEGORY_IDS:
        cat_url = f"{BASE_URL}/?mode=cate&cbid=2862352&csid={csid}"
        soup = fetch_page(cat_url)
        for a in soup.select('a[href*="pid="]'):
            href = a.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if m:
                urls.add(f"{BASE_URL}/?pid={m.group(1)}")
    return sorted(urls)


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
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

    parsed = parse_product(title)

    variants = product.get("variants") or []
    price = product.get("sales_price_including_tax") or product.get("sales_price")
    weight_g = None
    weight_m = WEIGHT_PATTERN.search(title)
    if weight_m:
        weight_g = int(weight_m.group(1))
    elif variants:
        variant_weight_m = WEIGHT_PATTERN.search(variants[0].get("option1_value") or "")
        if variant_weight_m:
            weight_g = int(variant_weight_m.group(1))
            variant_price = variants[0].get("option_price_including_tax") or variants[0].get("option_price")
            if variant_price is not None:
                price = variant_price

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(price) if price is not None else None,
            "product_url": product_url,
        }

    structural_out_of_stock = product.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def pick_canonical_products(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[float, dict]] = {}
    for item in items:
        title = item["raw_name"]
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        base = WEIGHT_PATTERN.sub("", title)
        base = re.sub(r"\s+", " ", base).strip()
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    all_items = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            all_items.append(detail)

    records = pick_canonical_products(all_items)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeeboy.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeboy.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
