# -*- coding: utf-8 -*-
"""
scrape_towncoffee.py

タウンコーヒー(towncoffee.shop-pro.jp、和歌山県岩出市荊本235、自家焙煎豆
のオンライン販売)の商品情報を取得する。カラーミーショップ(旧ドメイン名
shop-pro.jpだが現行のカラーミーショップと同一プラットフォーム。var
Colorme構造も他のカラーミー店舗と同一)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【重量バリエーションについて】
実データ確認済み: 各銘柄がoption1_value(100g/200g/300g/500g)の
variantsを持ち、価格は重量に比例(例: ブラジルサントスは100g=702円、
200g=1404円…)。variantsから最小重量(100g)のoption_price_including_tax
を代表価格として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 全102件のうちカリタ/メリタ製のミル・ドリッパー・
濾紙・ポット等の器具、「コーヒーギフト」各種(詰め合わせ)、「〜な方に
ちょっとした手土産」(詰め合わせ)、「水出しアイスコーヒー」パック
(液体加工品、豆の抽出済み)が非対象。NON_BEAN_KEYWORDSで除外する。
なお「アイスコーヒーブレンド」は水出し用に焙煎された豆売り商品のため
対象に含める(「水出しアイスコーヒー」とは別表記で区別できる)。
残り54件(いずれも100/200/300/500gの重量選択制)を対象とする。

【商品名の「売れ筋ランキング」接頭辞について】
実データ確認済み: 一部商品名に「【売れ筋商品ランキング第N位】」の接頭辞
が付いている。産地・銘柄の判定を妨げるため、RANKING_PREFIX_PATTERNで
除去する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "タウンコーヒー",
    "url": "https://towncoffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "和歌山県岩出市荊本235",
    "prefecture": "和歌山県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://towncoffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "カリタ", "メリタ", "コーヒーギフト", "手土産", "水出しアイスコーヒー",
]
RANKING_PREFIX_PATTERN = re.compile(r"^【売れ筋商品ランキング第\d+位】\s*")
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def pick_min_weight_variant(variants: list[dict]) -> dict | None:
    weighted = []
    for v in variants:
        normalized = unicodedata.normalize("NFKC", v.get("option1_value") or "")
        m = WEIGHT_PATTERN.search(normalized)
        if m:
            weighted.append((int(m.group(1)), v))
    if not weighted:
        return None
    weighted.sort(key=lambda x: x[0])
    return weighted[0][1]


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
    title = RANKING_PREFIX_PATTERN.sub("", title).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    variants = product.get("variants") or []
    weight_g = None
    price = product.get("sales_price_including_tax") or product.get("sales_price")
    weighted_variant = pick_min_weight_variant(variants)
    if weighted_variant is not None:
        normalized = unicodedata.normalize("NFKC", weighted_variant.get("option1_value") or "")
        weight_m = WEIGHT_PATTERN.search(normalized)
        weight_g = int(weight_m.group(1)) if weight_m else None
        variant_price = weighted_variant.get("option_price_including_tax") or weighted_variant.get("option_price")
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
    with open("data_towncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_towncoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
