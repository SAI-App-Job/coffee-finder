# -*- coding: utf-8 -*-
"""
scrape_yodacoffee.py

養田珈琲(YODA COFFEE、yoda-coffee.shop-pro.jp、福島県いわき市小名浜南君ヶ塚町
10-30、SCAJ認定コーヒーマイスターが営む自家焙煎コーヒーショップ)の商品情報を
取得する。カラーミーショップ(shop-pro.jp、新テーマ"p-product-*"系クラス)。

【店舗発見の経緯】
全国再調査(福島県)でkankou-iwaki.or.jp観光サイト記事から発見。

【対象商品について】
実データ確認済み(2026-09時点): サイト内検索(?mode=srh)で見つかる全10件の
うち、ドリップバッグ(いわきハワイアンブレンド ドリップバック5個)を除いた
コーヒー豆9銘柄(全て100g)を対象とする。

【テーマについて】
実データ確認済み: 他のカラーミーショップ店舗(paradiso・karaku等)で使われる
旧テーマ(div.product_explain、li.productlist_list)とは異なる新テーマ
(div.p-product-explain__body、生産地・品種等の構造化ラベルなし)を使用。
商品説明は定型的なマーケティング文言のみで、farm_note相当の情報は
サイト上に無い。

【在庫状態について】
実データ確認済み: inventory_control設定が無効(stock_numは全商品null)の
ため構造的な在庫判定ができず、商品名のテキストのみで判定する
(detect_stock_status)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "養田珈琲",
    "url": "http://www.yodacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福島県いわき市小名浜南君ヶ塚町10-30",
    "prefecture": "福島県",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://yoda-coffee.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["ドリップバック", "ドリップバッグ"]


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    html = fetch_euc(f"{BASE_URL}?mode=srh&keyword=&sort=n")
    return sorted(set(re.findall(r"pid=(\d+)", html)))


def build_record(pid: str) -> dict | None:
    html = fetch_euc(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    colorme = json.loads(m.group(1))
    product = colorme.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    soup = BeautifulSoup(html, "html.parser")
    explain = soup.select_one("div.p-product-explain__body")
    flavor_notes = None
    if explain:
        for br in explain.find_all("br"):
            br.replace_with("\n")
        text = explain.get_text()
        text = re.sub(r"[＼／]{2,}[^\n]*\n?", "", text)  # 装飾的な見出し行を除去
        text = re.sub(r"\n{2,}", "\n", text).strip()
        flavor_notes = text or None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")
    stock_status = detect_stock_status(title)
    sold_out = stock_status != "販売中"

    url = f"{BASE_URL}?pid={pid}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    if parsed["category"] == "ブレンド":
        # 実データ確認済み: 「いわきハワイアンブレンド」はいわき市の別名
        # 「東北のハワイ」に由来するご当地ブレンドで、実際のハワイ産豆とは
        # 無関係。parse_product内の国名検出がブレンド名の「ハワイ」に
        # 反応してしまうため、ブレンドでは産地を明示的にクリアする
        # (デ・スティル コーフィーで確認済みの同種バグへの対処と同じ)。
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title) or (flavor_notes and detect_country_name(flavor_notes))
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

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
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in collect_product_ids():
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_yodacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yodacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
