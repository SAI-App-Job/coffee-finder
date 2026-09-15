# -*- coding: utf-8 -*-
"""
scrape_mikoya134.py

珈琲豆専門店 mikoya134(bueno珈琲豆専門店、mikoya134.shop-pro.jp、〒890-0056
鹿児島県鹿児島市下荒田3丁目37-1、自家焙煎豆のオンライン販売)の商品情報を
取得する。カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://mikoya134.shop-pro.jp/?mode=sk)で実データ確認済み
(2026-09時点): 「住所」欄に「鹿児島県鹿児島市下荒田3-37-1」との記載を確認。
候補リストの住所(3丁目37-1)と一致。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述
(User-agent: *はDisallow: /secure/, /cart/のみ。AhrefsBot等の特定クローラー
のみDisallow: /)。本スクレイパーは識別可能な独自User-Agentを使用する。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=EUC-JP)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「スペシャリティ珈琲豆」(cbid=2632936)が
唯一の単一銘柄コーヒー豆カテゴリで全9件。他のカテゴリ(LINEクーポン対象・
定期購入・セット・ドリップバッグ・水出しアイス珈琲・お試し品・ギフト・
珈琲器具)はいずれも非対象(定期購入・詰め合わせ・ドリップバッグ・
アイスコーヒー・器具、または「お試し品」カテゴリの3件のように銘柄不特定の
福袋的商品)のため除外する。

【重量・挽き方バリエーションについて】
実データ確認済み: 全9件が「豆/粉」×「100g/50g」の4バリアント構成(cart
JSON変数`Colorme.product.variants`のoption1_value)。挽いていない「豆」の
バリアントに限定し、その中から最小重量(50g)を採用する。なお2件
(エチオピア産ミチュ、グアテマラ産カフェ・ピューマSHB)は50gバリアントの
表示ラベルに旧価格と思われる金額(「650円」「520円」)が残っているが、
実際に課金される価格は構造化フィールド(option_price_including_tax)であり
100gと同額になっている(店舗側のラベル更新漏れと見られるが、実売価格を
正としてそのまま採用する)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲豆専門店 mikoya134",
    "url": "https://mikoya134.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "鹿児島県鹿児島市下荒田3丁目37-1",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述。User-agent: *はDisallow: /secure/, "
                          "/cart/のみ)",
}

BASE_URL = "https://mikoya134.shop-pro.jp"
BEAN_CATEGORY_ID = "2632936"  # スペシャリティ珈琲豆
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={BEAN_CATEGORY_ID}&csid=0")
    urls: list[str] = []
    seen: set[str] = set()
    for link in soup.select('a[href*="pid="]'):
        href = link.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not m:
            continue
        product_url = f"{BASE_URL}/?pid={m.group(1)}"
        if product_url not in seen:
            seen.add(product_url)
            urls.append(product_url)
    return urls


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


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if (v.get("option1_value") or "") == "豆"]
    pool = whole_bean or variants

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    pool = sorted(pool, key=weight_key)
    return pool[0] if pool else None


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = variant.get("option_price_including_tax") if variant else product.get("sales_price_including_tax")

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

    weight_g = None
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("title") or "")
        weight_g = int(m.group(1)) if m else None

    whole_bean_variants = [v for v in variants if (v.get("option1_value") or "") == "豆"]
    check_variants = whole_bean_variants or variants
    structural_out_of_stock = bool(check_variants) and all(
        v.get("stock_num") == 0 for v in check_variants
    )
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
    product_urls = fetch_product_urls()

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
    import json as json_module

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mikoya134.json", "w", encoding="utf-8") as f:
        json_module.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mikoya134.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
