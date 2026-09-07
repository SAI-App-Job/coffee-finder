# -*- coding: utf-8 -*-
"""
scrape_akafujicoffee.py

赤富士珈琲(akafuji-coffee.shop-pro.jp、静岡県富士宮市北町19-7、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミー/Shop-Proファミリー。公式
サイト(akafuji-coffee.com)はWordPress製の案内ページのみで、実際の通販機能は
akafuji-coffee.shop-pro.jp(カラーミーショップ)側にある(公式サイトのリンク
から確認済み)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全57件): 深煎り/オーガニック/マスターおすすめ各コーヒー
セット・水出しアイスコーヒー(ドリップバッグ付き)ギフト各種・マスター
おまかせコーヒーギフト・ドリップバッグのギフト(2/3種類)・水出しアイス
コーヒー(25g×6個入り)・カフェ・バッハ製ペーパーフィルター/ドリッパー/
サーバー(器具)・オリジナルキャニスター缶・ハリオ　メジャースプーン(器具)・
『保護猫支援プロジェクト』ベルソーブレンド10個(個包装、ドリップバッグ
相当の個包装形態)が非対象。特に「ドリップバッグ（10個入）」は各銘柄の
商品名先頭に<br>タグ区切りで付与されており(例:「ドリップバッグ（10個入）
<br>「たね」のブレンド（中煎り）」)、<br>を空白に正規化した後で
NON_BEAN_KEYWORDSと照合することで確実に除外できる。残り21件を対象と
する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "赤富士珈琲",
    "url": "https://akafuji-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "静岡県富士宮市北町19-7",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://akafuji-coffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "セット", "ギフト", "ドリップバッグ", "ペーパーフィルター", "ドリッパー",
    "サーバー", "キャニスター", "メジャースプーン", "水出しアイスコーヒー", "個包装",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ㎏]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


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
    price = product.get("sales_price_including_tax") or product.get("sales_price")

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
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = None
    if weight_m:
        weight_g = int(weight_m.group(1)) * 1000 if "㎏" in weight_m.group(0) else int(weight_m.group(1))

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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
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
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_akafujicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_akafujicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
