# -*- coding: utf-8 -*-
"""
scrape_roastermamenoki.py

豆の樹(Roaster Mamenoki、roaster-mamenoki.com、〒812-0017
福岡市博多区美野島3-12-11、注文後焙煎の自家焙煎豆専門店)の商品情報を
取得する。カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://roaster-mamenoki.com/?mode=sk)の「住所」欄には
ネットショップ作成サービス「カラーミーショップ」を運営するGMOペパボ
株式会社の東京都渋谷区の住所が明記の上「返品等の対応はしない」と
注記されている(プロキシ住所)。実店舗の住所はトップページ本文
(https://roaster-mamenoki.com/)に「〒812-0017 福岡市博多区美野島
3-12-11」と直接記載されていることを確認済み(2026-09時点)。事前調査の
候補住所「西月隈3-12-11」は町名が誤り(正しくは「美野島」)だったため
訂正して採用する。

【文字コードについて】
実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【テーマについて】
実データ確認済み: `li.c-item-list__item`テーマ(縁の木/井の頭珈琲と同系統)。
一覧ページの時点で商品名(.c-item-list__ttl)・価格(.c-item-list__price、
内税)が静的HTMLで直接出力されているため、詳細ページへの個別アクセスは
行わない。

【重量について】
実データ確認済み: 商品名に【200g】のように角括弧で重量が明記されている。

【非コーヒー豆商品の除外について】
実データ確認済み(全26件): アーモンド・ピスタチオ(生ナッツの自家焙煎)が
コーヒー豆と異なる商品カテゴリとして存在する。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): shop-pro.jp標準の記述で、本スクレイパーが
使う一覧ページ(?mode=srh)は制限対象外。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆の樹",
    "url": "https://roaster-mamenoki.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県福岡市博多区美野島3-12-11",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、"
                          "本スクレイパーが使う一覧ページは制限対象外)",
}

BASE_URL = "https://roaster-mamenoki.com"
LIST_BASE_URL = "https://roaster-mamenoki.com/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
MAX_PAGES = 20

NON_BEAN_KEYWORDS = ["アーモンド", "ピスタチオ"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.c-item-list__item"):
        name_el = li.select_one(".c-item-list__ttl a")
        if not name_el:
            continue
        title = name_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        href = name_el.get("href", "")
        m_pid = re.search(r"pid=(\d+)", href)
        product_url = f"{BASE_URL}/?pid={m_pid.group(1)}" if m_pid else href

        price = None
        price_el = li.select_one(".c-item-list__price")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        items.append({"raw_name": title, "product_url": product_url, "price": price})
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
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "weight_g": weight_g,
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
    with open("data_roastermamenoki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roastermamenoki.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
