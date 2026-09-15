# -*- coding: utf-8 -*-
"""
scrape_vincoffee.py

Vin COFFEE(vincoffee.com、〒836-0046 福岡県大牟田市本町1-1-1、
自家焙煎コーヒー豆専門店)の商品情報を取得する。カラーミーショップ
(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://vincoffee.com/?mode=sk)で「836-0046 福岡県
大牟田市本町1-1-1」を確認済み(2026-09時点、EUC-JPで直接デコードして
確認)。

【文字コードについて】
実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【テーマについて】
実データ確認済み: `dd`要素の中に`p.item_title`(商品名リンク)・
`p.price_search`(価格、税込)・`p.item_explain`(簡単な説明文)が並ぶ
独自テーマ。一覧ページの時点で商品名・価格が静的HTMLで直接出力されて
いるため、詳細ページへの個別アクセスは行わない。

【重量について】
実データ確認済み: 商品名(「きらきら星／きらきらぼし（中煎りブレンド）」等)に
重量表記が無い(バリエーション選択制と推測されるが一覧からは不明)ため
weight_gは常にnullとする。

【非コーヒー豆商品の除外について】
実データ確認済み: ドリップバッグ・マスターセレクト(複数銘柄の詰め合わせ
セット、ギフト専用商品含む)が非対象。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): shop-pro.jp標準の記述で、本スクレイパーが
使う一覧ページ(?mode=srh)は制限対象外。
"""

import re

import requests
from bs4 import BeautifulSoup, NavigableString

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Vin COFFEE",
    "url": "https://vincoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県大牟田市本町1-1-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、"
                          "本スクレイパーが使う一覧ページは制限対象外)",
}

BASE_URL = "https://vincoffee.com"
LIST_BASE_URL = "https://vincoffee.com/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
MAX_PAGES = 20

NON_BEAN_KEYWORDS = ["ドリップバッグ", "マスターセレクト", "マスター・セレクト", "ギフト"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = []
    for dd in soup.select("dd"):
        title_p = dd.select_one("p.item_title")
        link_el = dd.select_one("p.item_title a")
        if not title_p or not link_el:
            continue
        # 実データ確認済み: `<a href="?pid=N" />`が自己終了タグとして解釈され、
        # 商品名テキストがa要素の外(p.item_title直下のテキストノード)に
        # 置かれる壊れたHTML構造のため、a.get_text()ではなくp.item_title直下の
        # テキストノードのみを取り出す(価格・説明文は入れ子のpタグなので混入しない)。
        title = "".join(
            str(c) for c in title_p.contents if isinstance(c, NavigableString)
        ).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        href = link_el.get("href", "")
        m_pid = re.search(r"pid=(\d+)", href)
        if not m_pid:
            continue
        product_url = f"{BASE_URL}/?pid={m_pid.group(1)}"

        price = None
        price_el = dd.select_one("p.price_search")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        explain_el = dd.select_one("p.item_explain")
        explain = explain_el.get_text(strip=True) if explain_el else None

        items.append({
            "raw_name": title,
            "product_url": product_url,
            "price": price,
            "explain": explain,
        })
    return items


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": item["product_url"],
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
        "flavor_notes": item.get("explain"),
        "blend_components": [],
        "price": item["price"],
        "weight_g": None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_items = []
    seen_urls = set()
    page = 1
    while page <= MAX_PAGES:
        items = scrape_list_page(page)
        new_items = [i for i in items if i["product_url"] not in seen_urls]
        if not new_items:
            break
        for i in new_items:
            seen_urls.add(i["product_url"])
        all_items.extend(new_items)
        page += 1

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import json

    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_vincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_vincoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
