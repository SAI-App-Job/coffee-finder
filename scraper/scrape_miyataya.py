# -*- coding: utf-8 -*-
"""
scrape_miyataya.py

宮田屋珈琲(miyataya.shop-pro.jp、札幌市清田区清田1条3丁目1-66、
カラーミーショップ/shop-pro.jp)の商品情報を取得する。

住所は特定商取引法ページ(https://miyataya.shop-pro.jp/?mode=sk)で実データ
確認済み(2026-09時点、〒004-0841 北海道札幌市清田区清田1条3丁目1-66)。

【プラットフォームについて】
RITARU COFFEE/石田珈琲店と同じくprd_lst_*クラスを使わない別テーマ
(一覧はpid付き<a>のみ、価格・重量等は商品詳細ページのvar Colorme JSONから
取得)。

【対象カテゴリについて】
実データ確認済み: 「ストレート豆」(cbid=2234721、10件)と「ブレンド豆」
(cbid=2234720、10件)の計20件を対象とする。「生豆」(cbid=2234722)は未焙煎の
生豆のため対象外(プロジェクト方針: 生豆のみの商品は非対象)、「ギフト商品」
「お買い得商品」「毎月届く10%OFF定期便」も非対象(お買い得・定期便は
上記2カテゴリと重複する銘柄の可能性が高く、生の単一銘柄情報としては
上記2カテゴリで十分)。

【重量・価格について】
実データ確認済み: 挽き方(標準挽き/粗挽き/細挽き/エスプレッソ用/豆のまま)の
バリアントがあるが、挽き方に関わらず同一価格。重量は商品名に「100g」等の
形で埋め込まれておりバリアント自体には重量情報が無いため、商品名から
正規表現で抽出する。

robots.txt確認済み(2026-09時点): 他のshop-pro.jp系店舗と同一の記述。

【flavor_notes(2026-09-20追記)】
実データ確認済み: 詳細ページのdiv.p-product-explain__body内(「DETAIL」
セクション)に短いテイスティング文が入っている(対象20件全てで確認)。
既存のColorme JSON取得と同じHTML取得を再利用するため追加のHTTP
アクセスは不要。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "宮田屋珈琲",
    "url": "https://miyataya.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市清田区清田1条3丁目1-66",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。他のshop-pro.jp系店舗と同一の記述。"
                          "User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://miyataya.shop-pro.jp/"
CATEGORY_URLS = [
    "https://miyataya.shop-pro.jp/?mode=cate&cbid=2234721&csid=0",  # ストレート豆
    "https://miyataya.shop-pro.jp/?mode=cate&cbid=2234720&csid=0",  # ブレンド豆
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
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


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.p-product-explain__body")
    text = el.get_text(" ", strip=True) if el else None
    return text or None


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        for key in ("option1_value", "option2_value"):
            m = WEIGHT_PATTERN.search(variant.get(key) or "")
            if m:
                return int(m.group(1))
    m = WEIGHT_PATTERN.search(fallback_text or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def is_whole_bean(v):
        return "豆のまま" in (v.get("option1_value") or "") or "豆のまま" in (v.get("option2_value") or "")

    whole_bean = [v for v in variants if is_whole_bean(v)]
    pool = whole_bean or variants
    return pool[0]


def build_record(product_url: str, fallback_title: str) -> dict | None:
    soup = fetch_page(product_url)
    colorme_product = extract_colorme_product(soup)
    variants = (colorme_product or {}).get("variants") or []
    if not colorme_product or not variants:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": fallback_title,
            "non_bean": True,
            "product_url": product_url,
        }

    title = (colorme_product.get("name") or fallback_title).strip()
    parsed = parse_product(title)
    variant = pick_canonical_variant(variants)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else None,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(title)

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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_from_variant(variant, title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cat_url in CATEGORY_URLS:
        for item in scrape_list_page(cat_url):
            items_by_url.setdefault(item["product_url"], item)

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        try:
            detail = build_record(product_url, item["raw_name"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
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
    with open("data_miyataya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_miyataya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
