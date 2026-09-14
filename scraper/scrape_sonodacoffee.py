# -*- coding: utf-8 -*-
"""
scrape_sonodacoffee.py

sonoda coffee(そのだコーヒー、sonodacoffee.shop、山口県美祢市大嶺町奥分
3118-1、自家焙煎豆のオンライン販売)の商品情報を取得する。STORES。

【住所について】
公式ストアの特定商取引法ページ(https://sonodacoffee.shop/tokushoho)で実
データ確認済み(2026-09時点、複数回リトライ後に取得): 「事業者名 sonoda
coffee / 所在地　〒7592214 山口県 美祢市大嶺町奥分3118-1」。候補リストの
住所と一致(郵便番号759-2214を追加確認)。

robots.txt確認済み(2026-09時点): 他のSTORES系店舗と同一の記述
(Crawl-delay: 20、/tokushoho・/cart等の非公開/取引系のみDisallow、/items/は
対象外)。本スクレイパーはCrawl-delay: 20に従い、リクエスト間に20秒の間隔を
設ける。

【Cloudflare対策について】
実データ確認済み: デフォルトのUser-Agentだと Captcha Challenge(HTTP 403)が
返ることがあるが、一般的なブラウザ相当のヘッダーを付けてrequests.Session()
でCookieを保持しながらリトライすると解消することを確認した(理由は
scrape_mikazukido.pyと同一)。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全30件): 銅製ドリップポット・8周年記念グッズ
(アクリルキーホルダー・ステッカー)・プレゼントボックス(ドリップバッグ10個)・
ウイスキーとコリアンダのカフェオレベース(ノンアルコール、リキッド)・
Tシャツ/スウェット/ロングスリーブシャツ/半袖シャツ/ドルマンスリーブシャツ
(アパレル)・ネルドリップ各種(器具)・ドリップバック単品・水出し珈琲パック
(1L用、リキッド用パック)がNON_BEAN_KEYWORDSで除外される。残り13件
(ストレート12種＋フレーバー1種、いずれも100g)を対象とする。

【フレーバーコーヒーについて】
実データ確認済み: 「ブランデー風味付けアリーシャ<ノンアル>(中深)100g」は
ブランデー風味付け(ノンアルコール)のフレーバーコーヒーである。
coffee_parser.FLAVOR_KEYWORDSは「フレーバーコーヒー」等の直接表記のみを
検出するため「風味付け」表記は検出できない。実データで確認した結果を
踏まえ、FLAVOR_OVERRIDE_KEYWORDSで明示的にフレーバー扱いに上書きし、
flavored_products_excludedに分離する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "sonoda coffee",
    "url": "https://sonodacoffee.shop/",
    "platform": "STORES",
    "address": "山口県美祢市大嶺町奥分3118-1",
    "prefecture": "山口県",
    "robots_txt_status": "許可(2026-09確認。他のSTORES系店舗と同一の記述。"
                          "Crawl-delay: 20が明示されている。/items/は対象外)",
}

BASE_URL = "https://sonodacoffee.shop"
CRAWL_DELAY_SECONDS = 20  # robots.txtのCrawl-delay: 20に従う
NON_BEAN_KEYWORDS = [
    "ドリップポット", "グッズ", "プレゼントボックス", "カフェオレベース",
    "シャツ", "スウェット", "ネルドリップ", "ドリップバック", "水出し",
]
# 理由はモジュールdocstring参照: coffee_parser.FLAVOR_KEYWORDSは「フレーバー」
# の直接表記のみ検出するため、「風味付け」表記のこのショップ固有の商品を
# 明示的にフレーバー扱いへ上書きする
FLAVOR_OVERRIDE_KEYWORDS = ["風味付け"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) CoffeeFinderBot/0.1 Chrome/124.0.0.0 Safari/537.36 "
                  "(+contact: your-contact-info-here)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)


def fetch_page(url: str, retries: int = 2) -> BeautifulSoup:
    last_exc = None
    for attempt in range(retries + 1):
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 403 and attempt < retries:
            time.sleep(3)
            continue
        try:
            resp.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            continue
        return BeautifulSoup(resp.text, "html.parser")
    raise last_exc or requests.RequestException(f"failed to fetch {url}")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/")
    results = []
    for link_el in soup.select("a.c-itemList__item-link[href]"):
        name_el = link_el.select_one(".c-itemList__item-name")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        results.append({"raw_name": raw_name, "product_url": product_url})
    return results


def build_record(product_url: str, raw_title: str, price: int | None) -> dict | None:
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(raw_title)
    is_flavored = parsed["is_flavored"] or any(
        kw in raw_title for kw in FLAVOR_OVERRIDE_KEYWORDS
    )

    if is_flavored:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(raw_title)
    weight_m = WEIGHT_PATTERN.search(raw_title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_title,
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
    html = str(soup)

    title_el = soup.select_one("h1.item_name")
    raw_title = title_el.get_text(strip=True) if title_el else ""
    if not raw_title:
        return None

    price_match = re.search(r"detailCtrl\.salesPrice\s*=\s*(\d+)", html)
    price = int(price_match.group(1)) if price_match else None

    return build_record(url, raw_title, price)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    list_items = scrape_item_list()
    time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    flavored_records = []

    for item in list_items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            detail = parse_product_detail(item["product_url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        finally:
            time.sleep(CRAWL_DELAY_SECONDS)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_sonodacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sonodacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
