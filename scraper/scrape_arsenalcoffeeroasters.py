# -*- coding: utf-8 -*-
"""
scrape_arsenalcoffeeroasters.py

ARSENAL Coffee Roasters(arsenalcoffeeroasters.shop、香川県高松市兵庫町2-1、
自家焙煎豆のオンライン販売)の商品情報を取得する。STORES(独自ドメイン)。

【住所について】
実データ確認済み(2026-09時点): 公式ストアの特定商取引法ページ
(https://arsenalcoffeeroasters.shop/tokushoho)で「会社名 株式会社八蔵 /
所在地 〒7600024 香川県 高松市兵庫町2-1 / 電話番号 0878843995」と表示され、
これは他のSTORES系店舗で見られるSTORES社自身のプロキシ住所ではなく、本
ショップ自身の実在の住所・電話番号(第三者情報源の高松経済新聞・かがわ
らいふ等で一致確認済み)。候補リストの住所と一致確認済み。

robots.txt確認済み(2026-09時点): 他のSTORES系店舗と同一の記述
(Crawl-delay: 20。/items/は対象外)。本スクレイパーはrobots.txtの
Crawl-delay: 20に従い、リクエスト間に20秒の間隔を設ける。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全5件): 「ARSENALオリジナルトートバッグ」・
「ARSENALオリジナルエコバック」・「ARSENALオリジナルステッカー」(雑貨)が
非対象。残り2件(ARSENAL DARK BLEND・ARSENAL LIGHT BLENDの各ブレンド)が対象。

【重量違いの重複について】
実データ確認済み: 各銘柄が100g(¥1,700)/200g(¥2,200)の2サイズのバリアント
構成(商品一覧では価格帯として「¥1,700～¥2,200」と表示)。商品詳細ページの
detailCtrl.addCart(...)呼び出しに埋め込まれたバリアントJSON
({"id":...,"name":"100g","salesPrice":1700,"quantity":10,...}等)から
全バリアントを抽出し、最小重量(100g)を代表として採用する(scrape_novoldcoffee.py
と同様の方針)。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ARSENAL Coffee Roasters",
    "url": "https://arsenalcoffeeroasters.shop/",
    "platform": "STORES",
    "address": "香川県高松市兵庫町2-1",
    "prefecture": "香川県",
    "robots_txt_status": "許可(2026-09確認。他のSTORES系店舗と同一の記述。"
                          "Crawl-delay: 20が明示されている。/items/は対象外)",
}

BASE_URL = "https://arsenalcoffeeroasters.shop"
CRAWL_DELAY_SECONDS = 20  # robots.txtのCrawl-delay: 20に従う
NON_BEAN_KEYWORDS = ["トートバッグ", "エコバック", "エコバッグ", "ステッカー"]
ADD_CART_PATTERN = re.compile(r"detailCtrl\.addCart\((\{.*?\})", re.S)

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
            # 理由は他のSTORES系スクレイパーと同様(Cloudflareの一時的なチャレンジ)
            time.sleep(3)
            continue
        try:
            resp.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            continue
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    raise last_exc or requests.RequestException(f"failed to fetch {url}")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/items")
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


def extract_variants(html_text: str) -> list[dict]:
    variants = []
    for m in ADD_CART_PATTERN.finditer(html_text):
        raw_json = html.unescape(m.group(1))
        try:
            variants.append(json.loads(raw_json))
        except json.JSONDecodeError:
            continue
    return variants


def weight_from_variant(variant: dict) -> int | None:
    m = re.search(r"(\d+)\s*[gｇ]", variant.get("name") or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def weight_of(v: dict) -> float:
        return weight_from_variant(v) if weight_from_variant(v) is not None else float("inf")

    min_weight = min(weight_of(v) for v in variants)
    return next(v for v in variants if weight_of(v) == min_weight)


def build_record(product_url: str, raw_title: str, variants: list[dict]) -> dict | None:
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(raw_title)
    variant = pick_canonical_variant(variants)
    price = variant.get("salesPrice") if variant else None
    weight_g = weight_from_variant(variant) if variant else None

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

    same_weight_variants = [v for v in variants if weight_from_variant(v) == weight_g]
    check_variants = same_weight_variants or variants
    all_out_of_stock = bool(check_variants) and not any((v.get("quantity") or 0) > 0 for v in check_variants)
    stock_status = detect_stock_status(raw_title, all_out_of_stock)

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
    html_text = str(soup)

    title_el = soup.select_one("h1.item_name")
    raw_title = title_el.get_text(strip=True) if title_el else ""
    if not raw_title:
        return None

    variants = extract_variants(html_text)
    return build_record(url, raw_title, variants)


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
    import json as json_module

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_arsenalcoffeeroasters.json", "w", encoding="utf-8") as f:
        json_module.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_arsenalcoffeeroasters.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
