# -*- coding: utf-8 -*-
"""
scrape_eishuya.py

盈舟屋珈琲(eishuya.com、〒729-3101 広島県安芸高田市八千代町118-1、自家
焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(旧ドメインeishuya.shop-pro.jpは現在eishuya.comに301リダイレクト)。

【住所について】
特定商取引法ページ(https://eishuya.com/?mode=sk)を実データ確認したところ
「729-3101 広島県安芸高田市八千代町118-1」であることを確認した(2026-09
時点)。一部の商品ページのmeta descriptionには「広島県福山市の自家焙煎
コーヒーカフェ」という古い(移転前と思われる)店舗紹介文が残っているが、
特定商取引法ページの記載を正式な所在地として採用する。

robots.txt確認済み(2026-09時点): shop-pro.jp標準のrobots.txtで、本
スクレイパーが使う商品一覧・詳細ページ(?mode=cate, ?pid=)は制限対象外。

【対象カテゴリについて】
実データ確認済み: 商品カテゴリは「盈舟屋のブレンド(cbid=2215118)」
「盈舟屋のシングルオリジン(cbid=2215290)」「ドリップバッグ・水出し
コーヒー(cbid=2797410)」「プレミアムアイスコーヒー(cbid=2281449、瓶入り
完成品)」「ギフトセット(cbid=2215291)」「コーヒーグッズ(cbid=2215293)」
の6種類。ブレンド・シングルオリジンの2カテゴリのみを対象とする。

【商品情報の取得方法について】
実データ確認済み: 一覧ページ(ul.category-item > li)に商品名・価格
(税込)が直接出力されている。ブレンドカテゴリはさらに「【送料無料で
お届け】お試しAセット/Bセット」(複数銘柄詰め合わせ)を含むため
NON_BEAN_KEYWORDSで除外する。

【重量違いの重複について】
実データ確認済み: 各銘柄(ブレンドは焙煎度別、シングルオリジンは農園×
焙煎度別)ごとに100g/200gの2種類の重量で別商品ページが存在し、一覧
ページの価格は安い方(100g)が先に、高い方(200g)が後に並ぶ。一覧では
重量が明示されないため、同一商品名の中で最安価格の商品ページのみ詳細
取得し、詳細ページの「内容量：」欄から実際の重量を確認する(実データ
確認済み: 最安価格の商品ページは実際に100gだった)。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 詳細ページのdiv.product-detail-titletxtに短い
テイスティング文が直接入っている(対象14件全て確認、配送・支払方法等の
混入なし)。全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "盈舟屋珈琲",
    "url": "https://eishuya.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "広島県安芸高田市八千代町118-1",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、本スクレイパーが"
                          "使う商品一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://eishuya.com"
CATEGORY_IDS = [2215118, 2215290]  # 盈舟屋のブレンド, 盈舟屋のシングルオリジン
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_LABEL_PATTERN = re.compile(r"内容量[：:]\s*<span>\s*(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category(cbid: int) -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0"
    soup = fetch_page(url)
    items = []
    for li in soup.select("ul.category-item > li"):
        link_el = li.select_one('a[href^="?pid="]')
        name_a = li.select("p a")
        if not link_el or not name_a:
            continue
        title = name_a[0].get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price_ps = li.find_all("p")
        price = None
        if price_ps:
            m = PRICE_PATTERN.search(price_ps[-1].get_text())
            if m:
                price = int(m.group(1).replace(",", ""))
        items.append({"title": title, "price": price, "url": BASE_URL + "/" + link_el["href"]})
    return items


def pick_cheapest_per_title(items: list[dict]) -> list[dict]:
    by_title: dict[str, dict] = {}
    for item in items:
        if item["price"] is None:
            continue
        existing = by_title.get(item["title"])
        if existing is None or item["price"] < existing["price"]:
            by_title[item["title"]] = item
    return list(by_title.values())


def fetch_detail_fields(product_url: str) -> tuple[int | None, str | None]:
    try:
        resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None, None
    resp.encoding = "euc-jp"
    weight_m = WEIGHT_LABEL_PATTERN.search(resp.text)
    weight_g = int(weight_m.group(1)) if weight_m else None

    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    desc_el = soup.select_one("div.product-detail-titletxt")
    flavor_notes = desc_el.get_text("\n", strip=True) if desc_el else None
    return weight_g, (flavor_notes or None)


def build_record(item: dict) -> dict | None:
    title = item["title"]
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
    weight_g, flavor_notes = fetch_detail_fields(item["url"])

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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: list[dict] = []
    for cbid in CATEGORY_IDS:
        try:
            all_items.extend(scrape_category(cbid))
        except requests.RequestException as e:
            print(f"[warn] カテゴリ取得失敗: cbid={cbid} ({e})")

    canonical_items = pick_cheapest_per_title(all_items)

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
    with open("data_eishuya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_eishuya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
