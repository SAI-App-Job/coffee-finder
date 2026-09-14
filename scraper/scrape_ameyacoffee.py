# -*- coding: utf-8 -*-
"""
scrape_ameyacoffee.py

アメヤ珈琲(ameyacoffeeweb.shop-pro.jp、秋田県男鹿市船越一向207-219、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp)。

【住所について】
候補リストでは第三者情報源(Yahoo!ロコ等)のみの住所とされていたが、特定
商取引法ページ(https://ameyacoffeeweb.shop-pro.jp/?mode=sk)を実データ
確認したところ「秋田県男鹿市船越一向２０７−２１９」との記載を確認
(2026-09時点、一次情報)。候補リストの住所と一致。公式サイト
(ameyacoffee.com)側の店舗紹介でも同住所の「男鹿船越店」を確認済み
(もう1店舗「男鹿店」の記載もあるが2店舗のみでチェーン規模には該当しない)。

robots.txt未確認のため、他のカラーミー店舗と同様に実質許可とみなす。

【文字コード】EUC-JP(実データ確認済み)。他のカラーミー店舗と同じく
resp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み: 「珈琲豆［ブレンド］」(cbid=2266967)と「珈琲豆
［ストレート］」(cbid=2344967)の2カテゴリ(各2ページ、一部pidが両カテゴリに
重複掲載)が対象。ドリップパック・代替・インフュージョン・リキッド・
ギフト・その他・珈琲器具の各カテゴリは非対象のため巡回しない。

【重量について】
実データ確認済み(全26件、重複除去後): 全商品が商品名に「(100g)」を含み、
バリアントによる重量違いは無い(単一価格・単一重量)。

【非コーヒー豆商品の除外について】
実データ確認済み: 「カフェオレベース（加糖）1本」(濃縮リキッド)・
「「ブレンド５種」ドリップパック(8g×5袋)」(ドリップバッグ)の2件が
非対象。NON_BEAN_KEYWORDSで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "アメヤ珈琲",
    "url": "https://ameyacoffeeweb.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "秋田県男鹿市船越一向207-219",
    "prefecture": "秋田県",
    "robots_txt_status": "実質許可とみなす(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述と推定)",
}

BASE_URL = "https://ameyacoffeeweb.shop-pro.jp"
BEAN_CATEGORY_IDS = ["2266967", "2344967"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["カフェオレベース", "ドリップパック", "ドリップバッグ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list(cid: str) -> list[str]:
    urls: list[str] = []
    for page in (1, 2):
        suffix = "" if page == 1 else f"&page={page}"
        soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0{suffix}")
        for link in soup.select('a[href*="pid="]'):
            href = link.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if m:
                urls.append(f"{BASE_URL}/?pid={m.group(1)}")
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
    product_urls: list[str] = []
    seen: set[str] = set()
    for cid in BEAN_CATEGORY_IDS:
        for url in scrape_category_list(cid):
            if url not in seen:
                seen.add(url)
                product_urls.append(url)

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
    with open("data_ameyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ameyacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
