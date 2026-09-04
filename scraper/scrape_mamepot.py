# -*- coding: utf-8 -*-
"""
scrape_mamepot.py

自家焙煎珈琲まめぽっと(mamepot.com、茨城県つくば市谷田部)の商品情報を
取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【カテゴリ構造について】
実データ確認済み: 全268件という大規模カタログのうち、コーヒー豆単品を
指すのは「月替りおすすめコーヒー」(gid=717640)・「ブレンドコーヒー」
(gid=696441)・「ストレートコーヒー・産地別」(gid=696462)・
「ノンカフェインのコーヒー」(gid=712547)の4カテゴリのみ(計38件、
重複込み)。「ドリップバッグ」「パックでかんたん！水出しコーヒー」
「紅茶・フレーバーティー・中国茶」「ハーブティー」「コーヒー器具・
その他」は対象外のため触れていない。この4カテゴリの和集合を対象とする
(pid単位で自然に重複排除)。

【非コーヒー豆商品の除外について】
実データ確認済み: 対象4カテゴリ内に1件だけ「カフェインレスコーヒー
ブラジル ドリップバッグ10個」というドリップバッグ商品が混在するため
NON_BEAN_KEYWORDSで除外する。

【重量違いの重複について】
実データ確認済み: 各銘柄が100g/200g/300g/400g/500gの複数重量で個別
商品登録されている(全て同一単価×倍数の単純な重量比例、実データ確認
済み)。商品名から末尾の重量表記を取り除いた基準名でグルーピングし、
最小重量を代表として採用する(11銘柄相当)。

【商品情報の取得方法について】
実データ確認済み: 商品詳細ページに埋め込まれたJS変数`var Colorme =
{...}`のproduct.name/sales_price_including_tax/stock_numから商品名・
価格・在庫を取得する(焙煎処 縁の木・豆香房・萌季屋・豆NAKANO・TRIBE
COFFEEと同じ方式)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "まめぽっと",
    "url": "https://mamepot.com/",
    "platform": "カラーミーショップ",
    "address": "茨城県つくば市谷田部1-1",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://mamepot.com"
# 理由はモジュールdocstring参照
BEAN_CATEGORY_GIDS = ["717640", "696441", "696462", "712547"]
NON_BEAN_KEYWORDS = ["ドリップバッグ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*$")
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_category_pids(gid: str) -> list[str]:
    soup = fetch_page(f"{BASE_URL}/?mode=grp&gid={gid}")
    pids = set()
    for a in soup.select('a[href*="pid="]'):
        m = re.search(r"pid=(\d+)", a.get("href", ""))
        if m:
            pids.add(m.group(1))
    return list(pids)


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
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
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
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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


def pick_canonical_records(records: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for rec in records:
        base_name = TRAILING_WEIGHT_PATTERN.sub("", rec["raw_name"]).strip()
        weight_key = rec["weight_g"] if rec["weight_g"] is not None else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight = existing["weight_g"] if existing and existing["weight_g"] is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = rec
    return list(by_base_name.values())


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids: set[str] = set()
    for gid in BEAN_CATEGORY_GIDS:
        pids.update(fetch_category_pids(gid))

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for pid in pids:
        product_url = f"{BASE_URL}/?pid={pid}"
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

    records = pick_canonical_records(records)
    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = f"{BASE_URL}/?pid={sys.argv[1]}"
        result = build_record(fetch_page(url), url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_mamepot.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mamepot.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
