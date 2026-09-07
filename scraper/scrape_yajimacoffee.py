# -*- coding: utf-8 -*-
"""
scrape_yajimacoffee.py

yajimacoffee(yajimacoffee.shop-pro.jp、岐阜県、自家焙煎豆のオンライン
販売)の商品情報を取得する。カラーミーショップ(Shop-Pro)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【文字コードについて】
実データ確認済み: レスポンスがEUC-JPで返される(他のカラーミー店舗の
多くはUTF-8だが、本店舗はテーマ作成時期が古いためEUC-JPのまま)。
requestsのデフォルト自動判定に任せず、明示的にEUC-JPでデコードする。

【商品名と重量表記の分離について】
実データ確認済み: var Colorme JSON内のproduct.nameは国名+銘柄のみ
(例:「ブラジル　［ニブラ］」)で重量を含まない。重量・焙煎度・生産
処理情報はh2.product_nameに続くdiv.product_descriptionの自由記述
(「【内容量】200g」「【生産処理】ナチュラル」等の角カッコ見出し)に
のみ記載されているため、そちらから正規表現で抽出する。variants配列は
重量違いではなく挽き方(豆のまま/フレンチプレス/金属フィルター/
ペーパードリップ/エスプレッソ)の違いで、価格は全オプション共通。

【非コーヒー豆商品の除外について】
実データ確認済み: 全25件中、定期便(200g×2/×4、6ヶ月/12ヶ月コース、
単一銘柄と特定できない頒布会形式)・コーヒー豆ギフト{A}{B}(詰め合わせ)・
オリジナルDINEX 8oz MUG CUP(白×黒/黒×白、器具)が非対象。
NON_BEAN_KEYWORDSで除外する。また3件、h2.product_name自体が存在しない
(削除済みプレースホルダー、sales_price=0/stock_num=0)ため別途除外する。
残り14件(ストレート11種+ブレンド3種)を対象とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, detect_processing_method

SHOP_INFO = {
    "name": "YAJIMA COFFEE",
    "url": "http://yajimacoffee.jp/",
    "platform": "カラーミーショップ",
    "address": "岐阜県岐阜市大宮町1-8",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "http://yajimacoffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
RESPONSE_ENCODING = "euc_jp"

NON_BEAN_KEYWORDS = ["定期便", "ギフト", "MUG CUP", "DINEX"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_DESC_PATTERN = re.compile(r"内容量[】\]]\s*(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = RESPONSE_ENCODING
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    name_el = soup.select_one("h2.product_name")
    title = name_el.get_text(strip=True) if name_el else ""
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    desc_el = soup.select_one("div.product_description")
    description_text = desc_el.get_text(separator="\n") if desc_el else ""

    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    data = json.loads(m.group(1)) if m else {}
    product = data.get("product") or {}
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    parsed = parse_product(title)

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

    # 生産処理(精選方法)はh2.product_nameに続く自由記述にのみ書かれているため、
    # 商品名だけを見るparse_product()の結果を、説明文からの検出で補強する。
    processing_method = parsed["processing_method"] or detect_processing_method(description_text)

    weight_m = WEIGHT_DESC_PATTERN.search(description_text)
    weight_g = int(weight_m.group(1)) if weight_m else None

    # 実データ確認済み: inventory_control="none"(在庫数管理なし)のため、
    # stock_numは常にnull。構造化された品切れフラグは存在せず、商品名の
    # テキストのみで在庫状態を判定する。
    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
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
    with open("data_yajimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yajimacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
