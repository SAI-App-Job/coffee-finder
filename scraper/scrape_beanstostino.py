# -*- coding: utf-8 -*-
"""
scrape_beanstostino.py

珈琲中毒製作所/Beans Tostino(ビーンズ トスティーノ、beanstostino.com、
滋賀県野洲市市三宅2341-1、オーダーメイド焙煎(注文ごとに焙煎度・挽き方を
指定できる)のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp、beanstostino.shop-pro.jp)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【「生豆」表記について】
実データ確認済み: 商品名末尾に「/生豆100g」等の表記があるが、商品詳細
ページには「焙煎度」(浅煎/中煎/中深煎/深煎/おまかせ等)と「グラインド」
(豆のまま/細挽き/中細挽き/中挽き/粗挽き)を選択するオプション欄が
必ず設置されており、注文ごとに自家焙煎して発送するオーダーメイド
焙煎店であることを確認済み(店舗説明文「送料無料のオーダーメイド焙煎店
「ビーンズトスティーノ」です。」、およびshop.htmlページの「自家焙煎」
表記複数箇所)。「生豆」は発送前(焙煎前)の重量表記であり、家庭用の
生豆(未焙煎豆)販売ではないため対象に含める。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml掲載の全18件): 以下が非対象。
  - 「ディップスタイルコーヒー　ディープブルーAA」(150円、焙煎度/
    グラインドの選択オプションが無い単品ドリップサンプル)
  - 「水出しアイスコーヒー　アイスブレンド」(550円、同オプションが無い
    完成品の水出しコーヒーパック)
  - 「アイスコーヒー2本で1本おまけ」(2,000円、完成品ボトルコーヒーの
    まとめ買いセット)
  - 「カフェオレベース」(1,728円、コーヒー豆ではない加工品)
  - 商品名が空の削除済みプレースホルダー1件(pid=192683919、価格0円・
    stock_num 0)
残り13件(いずれも焙煎度選択オプション付きの単品豆・ブレンド)を対象と
する。うち「コロンビア」「トミオフクダ　ドライオンツリー」「カラメリッチ」
「サントアントニオ　プレミアムショコラ」「マイルドブレンド」
「トスティーノブレンド」「アイスブレンド」「エスメラルダ」
「ストロングブレンド」の9件は商品名末尾に「/生豆100g」表記があり
weight_g=100とする。「ビンタンリマ」「完全有機栽培 レテフォホ松中くん」
「ホンジュラス」の3件は商品名・商品詳細ページのいずれにも重量表記が
無いため、他店のパターンと同様にweight_gはNoneのままとする(推測しない)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲中毒製作所/Beans Tostino",
    "url": "https://beanstostino.com/",
    "platform": "カラーミーショップ",
    "address": "滋賀県野洲市市三宅2341-1",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://beanstostino.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ディップスタイルコーヒー", "水出しアイスコーヒー", "おまけ", "カフェオレベース",
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
    with open("data_beanstostino.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beanstostino.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
