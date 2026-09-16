# -*- coding: utf-8 -*-
"""
scrape_ishidacoffee.py

石田珈琲店(ishidacoffeeten.com、札幌市北区北16条西3丁目1-18、
カラーミーショップ/shop-pro.jp)の商品情報を取得する。

住所は特定商取引法ページ(https://ishidacoffeeten.com/?mode=sk)で実データ
確認済み(2026-09時点、〒001-0016 北海道札幌市北区北十六条西3-1-18)。

【プラットフォームについて】
トップページ(ishidacoffeeten.com、ishidacoffee.shop-pro.jpも同一内容)は
ブランディング用のランディングページで、実際のオンラインストアへの遷移
(?mode=f1)からカテゴリページ(?mode=cate&cbid=N)に入る。RITARU COFFEEと
同じくprd_lst_*クラスを使わない別テーマのため、一覧からは商品名とpidのみ
取得し、価格・重量は商品詳細ページのvar Colorme JSONから取得する。

【対象カテゴリについて】
実データ確認済み: 「ブレンド珈琲」(cbid=2461050、5件)と「ストレート珈琲」
(cbid=2461051、7件)の計12件を対象とする。「おすすめストレート」
(cbid=2937609)はストレート珈琲のおすすめ品を再掲載したサブセットのため
重複回避のため対象外、「ドリップパック・その他」「ギフト」は非対象。

【バリアントの並び順について】
実データ確認済み: RITARU COFFEE/405coffeeとは逆で、option1_valueに重量
(100g/200g)、option2_valueに挽き方(豆のまま/粉)が入る。重量・挽き方の
判定はどちらのフィールドも走査するようにして、店舗間の並び順の違いを
吸収する。

robots.txt確認済み(2026-09時点): 他のshop-pro.jp系店舗と同一の記述。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "石田珈琲店",
    "url": "https://ishidacoffeeten.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市北区北16条西3丁目1-18",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。他のshop-pro.jp系店舗と同一の記述。"
                          "User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://www.ishidacoffeeten.com/"
CATEGORY_URLS = [
    "https://www.ishidacoffeeten.com/?mode=cate&cbid=2461050&csid=0",  # ブレンド珈琲
    "https://www.ishidacoffeeten.com/?mode=cate&cbid=2461051&csid=0",  # ストレート珈琲
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

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if is_whole_bean(v)]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


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
    with open("data_ishidacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ishidacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
