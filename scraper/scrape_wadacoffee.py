# -*- coding: utf-8 -*-
"""
scrape_wadacoffee.py

和田珈琲(www.wadacoffee.com、青森県十和田市元町西２−５−２、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp、
独自ドメイン)。

【住所について】
特定商取引法ページ(https://www.wadacoffee.com/?mode=sk)で実データ確認済み
(2026-09時点): 「青森県十和田市元町西２−５−２」との記載を確認。候補
リストでは`?mode=f1`が404になり住所未確認とされていたが、このショップの
tokushoho相当ページは`?mode=sk`だった(他のカラーミー店舗の一部と同様)。

robots.txt未確認のため、他のカラーミー店舗と同様に実質許可とみなす。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=EUC-JP)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み: 単一カテゴリ(cbid=2144225)に全13件が登録されており、
2ページに分かれる(1ページ目12件+2ページ目1件)。

【重量について】
実データ確認済み: 商品名に重量表記が無く、variants配列のtitle
(例:「豆のまま（オススメです！）　×　200g」)に挽き方と重量が両方
含まれる(店舗によりoption1_value/option2_valueのどちらに重量が入るか
一定しないため、titleフィールドから直接重量を検出する)。product自体の
sales_price_including_taxは最小重量(200g)バリアントの価格と一致するため、
これをそのまま採用し、重量は最小価格のバリアントのtitleから取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全13件): 「初回限定お試しブレンド3種セット」(複数銘柄
詰め合わせ)・「簡単なのに本格派　水出しアイスコーヒーパック」(水出し
専用パック)・「ドリップパックコーヒー」(ドリップバッグ)・「店主おまかせ
コーヒーセット」(福袋的セット)の4件が非対象。NON_BEAN_KEYWORDSで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "和田珈琲",
    "url": "https://www.wadacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "青森県十和田市元町西２−５−２",
    "prefecture": "青森県",
    "robots_txt_status": "実質許可とみなす(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述と推定)",
}

BASE_URL = "https://www.wadacoffee.com"
BEAN_CATEGORY_ID = "2144225"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "水出し", "ドリップパック", "ドリップバッグ", "おまかせ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list(cid: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for page in (1, 2):
        suffix = "" if page == 1 else f"&page={page}"
        soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0{suffix}")
        for link in soup.select('a[href*="pid="]'):
            href = link.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if not m:
                continue
            product_url = f"{BASE_URL}/?pid={m.group(1)}"
            if product_url not in seen:
                seen.add(product_url)
                urls.append(product_url)
    return urls


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def pick_min_price_weight(product: dict, price: int | None) -> int | None:
    variants = product.get("variants") or []
    candidates = [v for v in variants if v.get("option_price_including_tax") == price]
    pool = candidates or variants
    if not pool:
        return None
    variant = min(pool, key=lambda v: v.get("option_price_including_tax") or float("inf"))
    m = WEIGHT_PATTERN.search(variant.get("title") or "")
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    weight_g = pick_min_price_weight(product, price)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return None
    return build_record(url, colorme_product)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = scrape_category_list(BEAN_CATEGORY_ID)

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
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
    with open("data_wadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wadacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
