# -*- coding: utf-8 -*-
"""
scrape_ritaru.py

RITARU COFFEE(shop.ritaru.com、カラーミーショップ/shop-pro.jp系)の商品情報を
取得する。

【住所について】
候補リストには「札幌市厚別区厚別中央3条26丁目3-8」(ロースタリー)とあったが、
特定商取引法ページ(https://shop.ritaru.com/?mode=sk)と公式サイトのADDRESS欄
(https://www.ritaru.com/)の両方で実データ確認した結果、現在の正しい住所は
「北海道札幌市中央区北3条西26丁目3-8」(郵便番号0640823)だった(2026-09時点)。
本スクレイパーはこちらの検証済み住所を採用する。

【プラットフォームについて】
405coffee/Rhizomagと同じshop-pro.jp系(var Colorme埋め込み)だが、一覧ページの
テーマはprd_lst_*クラスを使わない別テーマ(li要素ではなくproduct-list__photo
クラスの<a>で?pid=リンクを持つのみ、価格・在庫等は一覧に出ない)。そのため
一覧からは商品名とURLのみ取得し、価格・重量等は商品詳細ページのvar Colorme
JSONから取得する(pick_canonical_variant等は405coffee.pyと共通ロジック)。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆」カテゴリ(cbid=2678179)を対象とする。1ページ目
(24件)は単一銘柄のブレンド/ストレート、2ページ目(16件)は全て「〜PACK
GIFT」「メール便◯pack」等の複数銘柄セット/ギフトのため、2ページ目は
NON_BEAN_KEYWORDS(セット・GIFT)で除外する。

【variants が空の商品について】
実データ確認済み: 「ミルクブリューパック」「挽き / moiwa no ao 250g」の2件は
商品詳細ページのvar Colorme.product.variantsが空配列(価格取得不可)。
在庫終了で実質非公開になっていると見られるため、非コーヒー豆商品として
別枠に分離する。

robots.txt確認済み(2026-09時点): 405coffee/Rhizomag等の系列shop-pro.jpと
同一の記述(User-agent: *は/secure/と/cart/のみ制限)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "RITARU COFFEE",
    "url": "https://shop.ritaru.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市中央区北3条西26丁目3-8",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。405coffee等と同一の記述。"
                          "User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://shop.ritaru.com/"
BEANS_CATEGORY_URL = "https://shop.ritaru.com/?mode=cate&cbid=2678179&csid=0"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照(2ページ目は全て複数銘柄セット/ギフト)
NON_BEAN_KEYWORDS = ["セット", "GIFT", "ギフト", "pack", "PACK"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(url: str) -> list[dict]:
    soup = fetch_page(url)
    results = []
    seen_pids = set()
    for a in soup.select('a[href*="pid="]'):
        text = a.get_text(strip=True)
        href = a.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not text or not m:
            continue
        pid = m.group(1)
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        results.append({"raw_name": text, "product_url": f"{BASE_URL}?pid={pid}"})
    return results


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("option2_value") or "")
        if m:
            return int(m.group(1))
    m = WEIGHT_PATTERN.search(fallback_text or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def build_record(product_url: str, title: str) -> dict | None:
    soup = fetch_page(product_url)
    colorme_product = extract_colorme_product(soup)
    variants = (colorme_product or {}).get("variants") or []
    if not colorme_product or not variants:
        # 理由はモジュールdocstring参照(variants空=価格取得不可、実質非公開)
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    name = (colorme_product.get("name") or title).strip()
    parsed = parse_product(name)

    variant = pick_canonical_variant(variants)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else None,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_from_variant(variant, name),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    list_items = scrape_list_page(BEANS_CATEGORY_URL)

    records = []
    flavored_records = []
    non_bean_records = []
    for item in list_items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            detail = build_record(item["product_url"], item["raw_name"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue

        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_ritaru.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ritaru.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
