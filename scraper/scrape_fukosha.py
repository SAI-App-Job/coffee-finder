# -*- coding: utf-8 -*-
"""
scrape_fukosha.py

風光舎(shop.fukosha.jp、岩手県岩手郡雫石町長山堀切野8-7、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://shop.fukosha.jp/?mode=sk)で実データ確認済み
(2026-09時点): 「岩手県岩手郡雫石町長山堀切野8-7」との記載を確認。候補
リストの住所と一致。

robots.txt未確認のため、他のカラーミー店舗と同様に実質許可とみなす
(User-agent: *に対し/secure/・/cart/のみDisallowが標準的なカラーミーの
robots.txt)。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=EUC-JP)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象商品の取得方法について】
実データ確認済み: このショップにはカテゴリ一覧ページ(mode=cate)が無く、
トップページのナビゲーションは焙煎度別グループ(浅煎り/中煎り/中深煎り/
深煎り、mode=grp)のみで商品横断的な一覧にならない。代わりにsitemap.xml
(全24件のpid一覧)から全商品ページを直接取得する方式を採る。

【重量について】
実データ確認済み: 商品名自体には重量表記が無く、variants配列の
option1_value(例:"100g"/"200g")に重量が入っている。product自体の
sales_price_including_taxは最小重量(100g)バリアントの価格と一致する
ため、これをそのまま採用し、重量は最小価格のバリアントのoption1_valueから
取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全24件): 「ギフトボックス（中）」(220円、包装資材)と
「旅の三部作」(1890円、複数銘柄の詰め合わせセットと推定、単一銘柄の
特定ができない)の2件が非対象。NON_BEAN_KEYWORDSで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "風光舎",
    "url": "https://shop.fukosha.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "岩手県岩手郡雫石町長山堀切野8-7",
    "prefecture": "岩手県",
    "robots_txt_status": "実質許可とみなす(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述と推定。User-agent: *は/secure/・/cart/のみ"
                          "Disallow)",
}

BASE_URL = "https://shop.fukosha.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフトボックス", "三部作"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        loc.get_text(strip=True)
        for loc in soup.find_all("loc")
        if "pid=" in loc.get_text()
    ]


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def pick_min_price_weight(product: dict, price: int | None) -> int | None:
    variants = product.get("variants") or []
    candidates = [v for v in variants if v.get("option_price_including_tax") == price]
    pool = candidates or variants
    if not pool:
        return None
    variant = min(pool, key=lambda v: v.get("option_price_including_tax") or float("inf"))
    m = WEIGHT_PATTERN.search(variant.get("option1_value") or "")
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    weight_g = pick_min_price_weight(product, price)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return None
    return build_record(url, colorme_product)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_fukosha.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukosha.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
