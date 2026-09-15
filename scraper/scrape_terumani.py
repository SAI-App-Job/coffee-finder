# -*- coding: utf-8 -*-
"""
scrape_terumani.py

てるまに珈琲(terumani.base.shop、〒891-9112 鹿児島県奄美市名瀬幸町12番22号
もとじビル1階、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【ドメインについて】
実データ確認済み(2026-09時点): 候補リストの`terumani.com`は接続すると403
(WAFによる遮断と見られる)。`terumani.base.shop`(BASE標準ドメイン)のみ
稼働しており、本スクレイパーは全リクエストをこちらに送信する。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【住所について】
実データ確認済み(2026-09時点): 候補リストにあった`/pages/law`はBASEの
新しいテーマのSPAシェルを返すのみで内容が無い(JS実行が必要)。フッターの
実際のリンク先は`/law`(pagesプレフィックス無し)であり、そちらは通常の
サーバーサイドHTMLとして特定商取引法ページ本文を返す。
特定商取引法ページ(https://terumani.base.shop/law)で実データ確認済み:
事業者名「沖田新作」、所在地「〒8919112 鹿児島県奄美市名瀬幸町12番22号
もとじビル1階」との記載を確認(候補リストのAmami-shiと一致)。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。
sitemap.xmlの/items/配下に全6件。

【対象商品について】
実データ確認済み(全6件): ドリップバッグ単品・ドリップバッグセット(10g×10袋)・
「奄美群島産てるまにブレンド珈琲80g×2セット販売」(同一銘柄の2個セット)の
3件を除外すると、単一銘柄のコーヒー豆2銘柄
(「奄美群島産てるまにブレンド珈琲」80g、「てるまにオリジナルブレンド珈琲」
250g/500gの重量違い)が残る。NON_BEAN_KEYWORDSで除外する。

【重量違いの重複について】
実データ確認済み: 「てるまにオリジナルブレンド珈琲」のみ250g/500gの2種類の
重量が個別商品登録されている。商品名末尾の重量表記を除いた基準名で
グルーピングし、最小重量(250g)を代表として採用する(renshirocoffee.py等と
同じ方式)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "てるまに珈琲",
    "url": "https://terumani.base.shop/",
    "platform": "BASE",
    "address": "鹿児島県奄美市名瀬幸町12番22号もとじビル1階",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://terumani.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_TAIL_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ].*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = WEIGHT_TAIL_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item = {**item, "base_name": base, "weight_g": weight_g}
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    if not title:
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
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
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({"title": title, "price": fields["price"], "url": product_url})

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
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
    with open("data_terumani.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_terumani.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
