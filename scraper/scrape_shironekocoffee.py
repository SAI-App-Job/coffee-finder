# -*- coding: utf-8 -*-
"""
scrape_shironekocoffee.py

自家焙煎珈琲シロネコ(shironekocoffee.com、静岡県榛原郡吉田町住吉188-1、
2013年開業の自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全70件): アイスコーヒー(リキッド)・カフェオレベース・各種
コーヒーギフト/詰め合わせセット・ドリップバッグコーヒー各種・シロネコ
オリジナルマグカップ・手提げ紙袋(袋のみ)・カスカラシロップ・ドーナツ
ドリッパー/カリタ103ペーパーフィルター/TIMEMOREグラインダー(器具)・
コーヒーお試しセット(50g×3種、複数銘柄の詰め合わせ)・水出しコーヒー
バッグ・削除済みプレースホルダー「テスト」(price=1)が非対象。
NON_BEAN_KEYWORDSで除外する(「セット」「ギフト」「アイスコーヒー」を
含む商品名はすべて上記のいずれかに該当することを実データで確認済み)。

【重量違いの重複と店舗独自の命名パターンについて】
実データ確認済み: 主要銘柄(シロネコ/クロネコ/ショコラ各ブレンド、エチオピア、
ブラジル、ケニア、メキシコオーガニックデカフェ、東ティモール、季節の
ブレンド「秋」)は100g/お得な200g/1kgの最大3サイズで別商品登録されている。
しかし単純に重量表記を取り除くだけでは基準名が一致しない
(例:「シロネコブレンド 100g｜酸味なし！まろやかで毎日飲める中深煎り
コーヒー」と「シロネコブレンド 1kg【送料無料】一番人気をお得にまとめ買い！
酸味なし！まろやか珈琲」は重量以降の説明文がサイズごとに異なる)。
このため、(1)先頭の「送料無料！」等のノイズ接頭辞除去、(2)「【...】」
括弧内(量詳細・送料無料表記等)の除去、(3)残った文字列中の最初の重量
トークン(「お得な200g」「もっとお得な1kg」等、接頭語+数値+単位)を検出し、
その直前までを基準名として採用(直前が空の場合は直後を採用。「季節の
ブレンド「秋」」のもっとお得な1kg商品のように重量トークンが商品名より
前に来る書式に対応するため)、という専用の正規化ロジックを実装した。
実データで9銘柄24商品が正しく統合されることを確認済み。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "シロネコ",
    "url": "https://shironekocoffee.com/",
    "platform": "カラーミーショップ",
    "address": "静岡県榛原郡吉田町住吉188-1",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://shironekocoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ギフト", "アイスコーヒー", "カフェオレベース", "ドリップバッグコーヒー",
    "マグカップ", "手提げ紙袋", "カスカラシロップ", "ドーナツドリッパー", "カリタ103",
    "コーヒーグラインダー", "お試しセット", "テスト", "水出しコーヒー バッグ", "セット",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_NUM_PATTERN = re.compile(r"(\d+)\s*(kg|ｋｇ|㎏|[gｇ])", re.IGNORECASE)
NOISE_PREFIX_PATTERN = re.compile(r"^(送料無料[!！]?|★)")
BRACKET_PATTERN = re.compile(r"[【\[][^】\]]*[】\]]")
WEIGHT_TOKEN_PATTERN = re.compile(r"(もっとお得な|お得な|お試し)?\s*\d+\s*(kg|ｋｇ|㎏|[gｇ])", re.IGNORECASE)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def extract_weight_g(text: str) -> int | None:
    m = WEIGHT_NUM_PATTERN.search(text)
    if not m:
        return None
    num = int(m.group(1))
    unit = m.group(2).lower()
    if unit in ("kg", "ｋｇ", "㎏"):
        return num * 1000
    return num


def canonical_base_name(title: str) -> str:
    t = NOISE_PREFIX_PATTERN.sub("", title)
    t = BRACKET_PATTERN.sub("", t)
    m = WEIGHT_TOKEN_PATTERN.search(t)
    if m:
        before = t[:m.start()].strip()
        after = t[m.end():].strip()
        t = before if before else after
    t = re.sub(r"[　\s]+", " ", t).strip()
    return t


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = canonical_base_name(item["title"])
        weight_key = extract_weight_g(item["title"]) or float("inf")
        existing = by_base_name.get(base_name)
        existing_weight = extract_weight_g(existing["title"]) if existing else None
        existing_weight = existing_weight if existing_weight is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    structural_out_of_stock = item.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_g = extract_weight_g(title)

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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    all_items = []
    for product_url in product_urls:
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        script_text = ""
        for script in soup.find_all("script"):
            text = script.string or script.get_text() or ""
            if "var Colorme" in text:
                script_text = text
                break
        m = COLORME_PATTERN.search(script_text)
        if not m:
            continue
        data = json.loads(m.group(1))
        product = data.get("product") or {}
        title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = product.get("sales_price_including_tax") or product.get("sales_price")
        all_items.append({
            "title": title,
            "price": int(price) if price is not None else None,
            "url": product_url,
            "stock_num": product.get("stock_num"),
        })

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
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
    with open("data_shironekocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shironekocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
