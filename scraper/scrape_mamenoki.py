# -*- coding: utf-8 -*-
"""
scrape_mamenoki.py

フレッシュローストコーヒー豆の木(coffee-mamenoki.jp、札幌市北区新琴似六条
14丁目7-31、EC-CUBE)の商品情報を取得する。同名(似た店名)の店舗が金沢市・
北九州市にも存在するが、本スクレイパーは特定商取引法ページ
(https://coffee-mamenoki.jp/shop/abouts/)で住所を実データ確認した
札幌市北区新琴似の店舗を対象とする。

【対象カテゴリについて】
実データ確認済み: 「オリジナルストレート」(category_id=23、11件)・
「オリジナルスペシャリティ」(category_id=22、5件)・「オリジナルブレンド」
(category_id=24、8件)・「オーガニックコーヒー」(category_id=21、1件)・
「カフェインレスコーヒー」(category_id=18、1件)の計26件を対象とする。
ナビゲーションに別途あった「アイスコーヒーリキッド」(category_id=14)は
コーヒー豆ではないため対象外。「アンデスマウンテン」はオーガニックコーヒー
とオリジナルブレンドの両カテゴリに重複掲載されているため、product_idで
重複排除する。

【一覧ページのみで完結する点について】
実データ確認済み: 一覧ページのdiv.list_area内に商品名(h3 a)・価格
(span[id^="price02_default_"])・品切れ状態(div.cartbtn.attentionの
有無)が全て揃っているため、詳細ページへの追加アクセスは行わない。

【重量について】
実データ確認済み: 全26件の商品名に「(200gかドリップバッグ10バッグ)」との
注記があり(一部「ブラジル サントス」等注記なしの商品もあるが同一商品ライン
のため同じ200gと判断)、豆のまま200gが基準の販売単位。ドリップバッグは
同一商品ページ内の挽き方選択肢の1つ(価格は据え置き)であり別商品ではない。

robots.txt確認済み(2026-09時点): /wp-admin/のみDisallow(本スクレイパーが
使う/shop/配下は制限対象外)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "フレッシュローストコーヒー豆の木",
    "url": "https://coffee-mamenoki.jp/shop/",
    "platform": "EC-CUBE",
    "address": "北海道札幌市北区新琴似六条14丁目7-31",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/のみDisallow、"
                          "/shop/配下は制限対象外)",
}

BASE_URL = "https://coffee-mamenoki.jp"
CATEGORY_IDS = [23, 22, 24, 21, 18]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
DEFAULT_WEIGHT_G = 200  # 理由はモジュールdocstring参照


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def build_record(box) -> dict | None:
    h3a = box.select_one('h3 a[href*="product_id="]')
    if not h3a:
        return None
    title = h3a.get_text(strip=True)
    href = h3a.get("href", "")
    product_url = f"{BASE_URL}{href}" if href.startswith("/") else href

    price_span = box.select_one('span[id^="price02_default_"]')
    price = None
    if price_span:
        m = re.search(r"[\d,]+", price_span.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    structural_out_of_stock = box.select_one("div.cartbtn.attention") is not None

    parsed = parse_product(title)

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else DEFAULT_WEIGHT_G
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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records_by_url: dict[str, dict] = {}
    flavored_by_url: dict[str, dict] = {}

    for cat_id in CATEGORY_IDS:
        url = f"{BASE_URL}/shop/products/list.php?category_id={cat_id}"
        try:
            soup = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            continue
        for box in soup.select("div.list_area"):
            detail = build_record(box)
            if detail is None:
                continue
            if detail.get("is_flavored"):
                flavored_by_url.setdefault(detail["product_url"], detail)
            else:
                records_by_url.setdefault(detail["product_url"], detail)

    return list(records_by_url.values()), list(flavored_by_url.values())


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mamenoki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamenoki.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
