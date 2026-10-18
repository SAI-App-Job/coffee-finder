# -*- coding: utf-8 -*-
"""
scrape_mamekoubouoita.py

珈琲屋豆工房(toki.ocnk.net、大分県別府市石垣東1-9-26、焙煎工房を兼ねた店舗)の
自家焙煎コーヒー豆の商品情報を取得する。おちゃのこネット(Ocnk)。

【店舗発見の経緯】
全国再調査(大分県)の新規発掘で発見。住所は特定商取引法表示(/info)および
店舗紹介(/page/3)で確認(大分県別府市石垣東1-9-26)。店舗紹介に「焙煎工房を
兼ねた店内で焙煎した新鮮な珈琲豆」の記載がある。

robots.txt確認済み(2026-10時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。

【商品一覧の取得方法について】
実データ確認済み: 珈琲豆カテゴリ(product-list/1)に200g袋の豆6件のみが載っている
(湯けむりブレンド・シンデレラブレンド・シグリAA・ウエウエテナンゴ・サンマリノ・
スプレモ)。全商品一覧にはさらにギフトセット(ドリップバッグ・カフェオレベース・
レギュラーコーヒー詰め合わせ)、カフェオレベース、コーヒー器具、オリジナルパッケージ
コーヒー(OEM印刷)があるが、いずれも自家焙煎豆単品ではないため対象外。
商品名は「〇〇-200g-」形式のため、重量(200g)は名前から取得し、表示名は末尾の
「-200g-」を外す。ストアは稼働中(カートボタンあり、お知らせ最新は2026-09-01)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲屋豆工房",
    "url": "https://toki.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "大分県別府市石垣東1-9-26",
    "prefecture": "大分県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは該当しない)",
}

BASE_URL = "https://toki.ocnk.net"
LIST_URL = f"{BASE_URL}/product-list/1"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"-(\d+)\s*g-")

# coffee_parser.pyで検出しにくい商品名からの産地・分類・焙煎度の明示(商品説明で確認済み)
BLEND_NAMES = ("湯けむりブレンド", "シンデレラブレンド")
ORIGIN_OVERRIDES = {
    "シグリAA (パプアニューギニア)": "パプアニューギニア",
    "ウエウエテナンゴ（グァテマラ）": "グアテマラ",
    "サンマリノ（ブラジル）": "ブラジル",
    "スプレモ（コロンビア）": "コロンビア",
}
ROAST_OVERRIDES = {"シンデレラブレンド": "中深煎り"}  # 説明文「中深煎りで苦味を抑え気味」


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_soup(LIST_URL)
    pids: list[str] = []
    # 一覧のカード内リンクのうち、サイドバーの固定バナー(product/71,238 = OEMパッケージ)は除く
    for a in soup.select('a[href*="/product/"]'):
        m = re.search(r"/product/(\d+)", a.get("href", ""))
        title = a.get_text(" ", strip=True)
        if m and WEIGHT_PATTERN.search(title) and m.group(1) not in pids:
            pids.append(m.group(1))
    return [f"{BASE_URL}/product/{pid}" for pid in pids]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    og = soup.select_one('meta[property="og:title"]')
    title_full = og["content"].strip() if og and og.get("content") else ""
    w = WEIGHT_PATTERN.search(title_full)
    if not title_full or not w:
        return None
    name = WEIGHT_PATTERN.sub("", title_full).strip()
    weight_g = int(w.group(1))

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one("div.item_desc_text")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)).strip()[:400] if desc_el else None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if name in BLEND_NAMES:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if name in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[name]
            parsed["origin_source"] = "raw_name"

    # カートボタンが無ければ品切れ扱い
    has_cart = soup.select_one('input[name="cart_add_btn"]') is not None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST_OVERRIDES.get(name) or parsed["roast_level"],
        "flavor_notes": desc,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if has_cart else "完売",
        "out_of_stock": not has_cart,
        "product_url": product_url,
    }


def scrape_all_products() -> list[dict]:
    urls = fetch_product_urls()
    records = []
    for url in urls:
        time.sleep(4)
        try:
            record = build_record(fetch_soup(url), url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_mamekoubouoita.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekoubouoita.json に出力しました")
