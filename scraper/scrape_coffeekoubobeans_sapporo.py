# -*- coding: utf-8 -*-
"""
scrape_coffeekoubobeans_sapporo.py

珈琲工房ビーンズ(合同会社fresh coffee beans、札幌市厚別区大谷地東5-5-26、
カラーミーショップ/shop-pro.jp)の商品情報を取得する。オンラインストアの
実ドメインはjikabaisen.com(屋号「自家焙煎.com」)。会社概要サイト
coffee-sapporo.net(WordPress、通販カート機能なし)とは別。

秋田県秋田市の同名店舗(珈琲工房ビーンズ、manual/shops/coffee-koubou-beans.json、
beans.crayonsite.net)とは無関係の別法人。特定商取引法ページ
(https://www.jikabaisen.com/?mode=sk)で住所を実データ確認済み(2026-09時点、
〒004-0041 札幌市厚別区大谷地東5-5-26)。

【プラットフォームについて】
RITARU COFFEE等と同じくprd_lst_*クラスを使わない別テーマ(一覧はpid付き
<a>のみ、価格等は商品詳細ページのvar Colorme JSONから取得)。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆」カテゴリ(cbid=71316、3ページ)を対象とする。
「コーヒーギフト」「セット」「器具類」「焼き立てナッツ」「読み物」は非対象。
カテゴリ内にも「ポストに届く2点セット」(2銘柄詰め合わせ)が1件あるため
NON_BEAN_KEYWORDSで除外する。

【重量について】
実データ確認済み: 全商品が「生豆220gを受注後焙煎」との表記で統一されており、
注文後に生豆から焙煎する形態(完全受注後焙煎)。他店舗(たまじ珈琲・大塚珈琲店
等)と同様、開示されているのは焙煎前の生豆重量のみで、焙煎後の正確な重量は
開示されていない。本スクレイパーはこの生豆重量(220g)をweight_gとして採用する。

【バリアントについて】
実データ確認済み: 焙煎度(おまかせ/ミディアム/ハイ/シティ/フルシティ/
フレンチ)×挽き方(豆のまま/各種挽き)の全組み合わせが同一価格。代表
バリアントとして「おまかせ」×「豆のまま」を優先的に採用する。

robots.txt確認済み(2026-09時点): 他のshop-pro.jp系店舗と同一の記述。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲工房ビーンズ（札幌市）",
    "url": "https://www.jikabaisen.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市厚別区大谷地東5-5-26",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。他のshop-pro.jp系店舗と同一の記述。"
                          "User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://www.jikabaisen.com/"
CATEGORY_PAGES = [
    "https://www.jikabaisen.com/?mode=cate&cbid=71316&csid=0",
    "https://www.jikabaisen.com/?mode=cate&cbid=71316&csid=0&page=2",
    "https://www.jikabaisen.com/?mode=cate&cbid=71316&csid=0&page=3",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["セット"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"生豆\s*(\d+)\s*[gｇ]")


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


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    for v in variants:
        if "おまかせ" in (v.get("option1_value") or "") and "豆のまま" in (v.get("option2_value") or ""):
            return v
    whole_bean = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    return (whole_bean or variants)[0]


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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
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
        "roast_level": None,  # 焙煎度は注文時に選択可能な変動要素のため未設定(roast_selectable扱い)
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_g,  # 生豆時の重量(焙煎後重量は開示なし。理由はdocstring参照)
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cat_url in CATEGORY_PAGES:
        for item in scrape_list_page(cat_url):
            if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
                continue
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
    with open("data_coffeekoubobeans_sapporo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeekoubobeans_sapporo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
