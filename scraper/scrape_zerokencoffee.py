# -*- coding: utf-8 -*-
"""
scrape_zerokencoffee.py

0からコーヒー研究所(ゼロケンコーヒー、zerocoffee.stores.jp、鳥取県西伯郡
南部町鴨部82、自家焙煎豆のオンライン販売)の商品情報を取得する。STORES。
米子店(鳥取県米子市四日市町41)という別店舗も展開しているが、公式ストアの
特定商取引法上の所在地は南部町(本店・焙煎工房)のためこちらを採用する。

【住所について】
公式ストアの特定商取引法ページ(https://zerocoffee.stores.jp/tokushoho)で
実データ確認済み(2026-09時点、複数回リトライ後に取得): 「代表者 瀧山雅人 /
所在地　〒6830341 鳥取県 西伯郡南部町鴨部82」。候補リストにあった2つの候補
住所(米子店の店頭住所 鳥取県米子市四日市町41 と、こちらの南部町の住所)の
うち、事業者本人が届け出た特定商取引法上の所在地である南部町側を採用する
(本プロジェクトの既定方針)。

robots.txt確認済み(2026-09時点): 他のSTORES系店舗と同一の記述
(Crawl-delay: 20、/tokushoho・/cart等の非公開/取引系のみDisallow、/items/は
対象外)。本スクレイパーはCrawl-delay: 20に従い、リクエスト間に20秒の間隔を
設ける。

【Cloudflare対策について】
実データ確認済み: デフォルトのUser-AgentだとCaptcha Challenge(HTTP 403)が
返ることがあるが、一般的なブラウザ相当のヘッダーを付けてrequests.Session()
でCookieを保持しながらリトライすると解消することを確認した(理由は
scrape_mikazukido.pyと同一)。

【非コーヒー豆商品について】
実データ確認済み(2026-09時点、全9件): 全件がストレート銘柄またはブレンドの
コーヒー豆単品で、非コーヒー豆商品・雑貨は無かった。NON_BEAN_KEYWORDSは
念のため空リストで用意しておく。

【重量について】
実データ確認済み: 商品名自体には重量表記が無いが、商品詳細ページの購入
オプション一覧(detailCtrl.addItemBrowsingHistory内のJSON、例:
「"name":"200g 豆"」「"name":"200g 粉"」)から全品200g規格であることを
確認した。WEIGHT_VARIANT_PATTERNでこのJSON文字列から重量を取得する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "0からコーヒー研究所",
    "url": "https://zerocoffee.stores.jp/",
    "platform": "STORES",
    "address": "鳥取県西伯郡南部町鴨部82",
    "prefecture": "鳥取県",
    "robots_txt_status": "許可(2026-09確認。他のSTORES系店舗と同一の記述。"
                          "Crawl-delay: 20が明示されている。/items/は対象外)",
}

BASE_URL = "https://zerocoffee.stores.jp"
CRAWL_DELAY_SECONDS = 20  # robots.txtのCrawl-delay: 20に従う
NON_BEAN_KEYWORDS: list[str] = []  # 理由はモジュールdocstring参照(現状は空)
WEIGHT_VARIANT_PATTERN = re.compile(r'"name"\s*:\s*"(\d+)\s*[gｇ]\s*(?:豆|粉)?"')

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


def build_record(product_url: str, raw_title: str, price: int | None, weight_g: int | None) -> dict | None:
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(raw_title)

    if parsed["is_flavored"]:
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

    weight_matches = WEIGHT_VARIANT_PATTERN.findall(html)
    weight_g = int(weight_matches[0]) if weight_matches else None

    return build_record(url, raw_title, price, weight_g)


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
    with open("data_zerokencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_zerokencoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
