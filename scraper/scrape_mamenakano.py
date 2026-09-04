# -*- coding: utf-8 -*-
"""
scrape_mamenakano.py

自家焙煎コーヒー豆 豆NAKANO(shop.mamenakano.com、千葉県)の商品情報を
取得する。カラーミーショップ。

【httpとhttpsについて】
実データ確認済み: `https://shop.mamenakano.com/`はSSL証明書のホスト名
不一致エラーになる(共有ホスティングの汎用証明書と推測)一方、サーバー
自体は`https://`への301応答自体は返し、その先が`http://`へのリダイレクト
になっている。実際のコンテンツはhttpで正常に配信されているため、
本スクレイパーは一貫してhttp URLを使用する。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗(萌季屋等)と同じ
記述。User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに列挙された全41件の`?pid=`商品を起点とし、
産地表示パターンで豆単品を判定する(後述)。

【豆単品の判定について】
実データ確認済み: 豆単品の商品名は例外なく「(英語の産地/デカフェ表記)
/ (日本語の産地・農園名)」という形式(例:「Tanzania / タンザニアAA
キリマンジャロ農園」「Decaf Mexico / デカフェ　メキシコ...」)。この
形式に一致しない商品(オリジナルグッズ・ドリップバッグ・サブスク
セット・器具等)を除外する。ただし「COFFEE MEASURE HOUSE / walnut」
「COFFEE MEASURE HOUSE / beech」(コーヒーメジャーカップの色違い商品)
のみこのパターンに偶然一致してしまうため、個別にNON_BEAN_KEYWORDSで
除外する。商品名が空の2件(削除済み商品と推測、価格・在庫とも0)も除外。
BEAN_PATTERNは全角スペースを含む場合があるtitleの先頭が英字である
ことのみを見る(【】付き接頭辞は事前に取り除く)。

【重量について】
実データ確認済み: 商品詳細ページの説明表(`table.table`内、
`td.cell_1`="容量"ラベル・`td.cell_2`=値)に「100g」が明記されている
(確認した全商品で100g固定)。焙煎処 縁の木・豆香房・萌季屋と同じ
`var Colorme = {...}`JS変数から商品名・価格・在庫を取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "豆NAKANO",
    "url": "http://shop.mamenakano.com/",
    "platform": "カラーミーショップ",
    "address": "千葉県",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同じ記述。"
                          "/secure/・/cart/のみDisallow、AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "http://shop.mamenakano.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["COFFEE MEASURE HOUSE"]
BRACKET_PREFIX_PATTERN = re.compile(r"^[\s　]*(?:【[^】]*】|［[^］]*］)[\s　]*")
BEAN_PATTERN = re.compile(r"^[A-Za-z]")
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "pid=" in text:
            urls.append(text.replace("https://", "http://"))
    return urls


def is_bean_product(title: str) -> bool:
    if not title.strip():
        return False
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return False
    stripped = BRACKET_PREFIX_PATTERN.sub("", title).strip()
    return bool(BEAN_PATTERN.match(stripped))


def extract_weight_g(soup: BeautifulSoup) -> int | None:
    for row in soup.select("table.table tr"):
        label_el = row.select_one("td.cell_1")
        value_el = row.select_one("td.cell_2")
        if not label_el or not value_el:
            continue
        if "容量" in label_el.get_text():
            m = WEIGHT_PATTERN.search(value_el.get_text())
            if m:
                return int(m.group(1))
    return None


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
    title = (product.get("name") or "").strip()
    if not is_bean_product(title):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": product.get("sales_price_including_tax") or product.get("sales_price"),
            "product_url": product_url,
        }

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    weight_g = extract_weight_g(soup)

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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            soup = fetch_page(product_url)
            detail = build_record(soup, product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail is None:
            continue
        if is_unchanged(prev, raw_name=detail["raw_name"]):
            records.append(prev)
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_mamenakano.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mamenakano.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
