# -*- coding: utf-8 -*-
"""
scrape_mameiribito.py

浜松自家焙煎 豆煎人(マメイリビト、mameiri.net、静岡県浜松市中央区原島町453-3、カフェ併設なし・
ご注文後に焙煎する自家焙煎の豆販売店)のオンラインショップの商品情報を取得する。
WordPress + WooCommerce系の独自EC(商品一覧HTML + 商品詳細ページ。WooCommerce Store API
(/wp-json/wc/store/v1/products)は404のため使わない)。

【店舗発見の経緯】
静岡県の再調査で「見送りの再発見」として登録。docs/not-implementable-shops.md(2026-09-07)では
「WooCommerce Store APIがGitHub Actions環境からのみ403」で見送られていた。本スクリプトは
Store APIを使わず、商品一覧ページ(/products/ 〜 /products/page/N/)と商品詳細ページのHTMLだけを
取得する。ローカル環境では全ページ200で取得できることを確認(2026-10-26)。CI環境からの再検証は別途必要。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧(全約150件)のうち、商品詳細ページの商品カテゴリーが
「コーヒー豆シングル」または「ブレンドコーヒー」のコーヒー豆のみを収録する。
次は除外: 大豆珈琲・黒大豆珈琲・小豆コーヒー(コーヒー豆ではない)、
「ヴィンテージ バレル ワイン」「ベトナム バレルエイジド カウダット」(ウイスキー樽熟成。説明に「インフューズドコーヒー」と明記)、
「まかないコーヒー 3」(カシャーサ樽熟成豆のブレンド)と
「カフェ・ヴィーニョ ロッソ スペシャル」(同商品を約20%ブレンド)、器具・食器・送料。
同一銘柄が100g版と200g版で別商品の場合は100g版を代表にし、200g版は除外する。
価格は商品ページの表示価格(税込、セール中は現行価格)で、販売単位は商品ページの
「販売価格は200g単位です」(一部のみ100g)の表記から取得する。焙煎度はご注文時に顧客が選択する方式のため
商品としての焙煎度は固定せず(roast_level=None)、roast_hintにその旨を保持する。
"""

import html
import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "浜松自家焙煎 豆煎人",
    "url": "https://mameiri.net/",
    "platform": "WordPress + WooCommerce系の独自EC",
    "address": "静岡県浜松市中央区原島町453-3",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(User-agent: * は /wp-admin/ のみ禁止。識別可能なUser-Agentを使用)",
    "source_note": "商品一覧(https://mameiri.net/products/ 〜 page/5)と各商品ページを2026-10-26に確認。住所は店舗概要https://mameiri.net/company/ に基づく。sitemapのlastmodは2026-10-25で更新は新しい。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://mameiri.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6
BEAN_CATEGORIES = ("コーヒー豆シングル", "ブレンドコーヒー")
EXCLUDE_TITLE_KEYWORDS = ("大豆", "小豆", "ヴィンテージ バレル ワイン", "ヴィーニョ ロッソ スペシャル", "ベトナム バレルエイジド", "カシャーサ", "郵送料")

ITEM_PATTERN = re.compile(r'<article class="c-item([^"]*)">.*?href="([^"]+)".*?c-item__ttl">([^<]*)<', re.S)
UNIT_PATTERN = re.compile(r"販売価格は\s*(\d+)\s*g\s*単位")


def get(url: str) -> requests.Response:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp


def list_items() -> list[dict]:
    items = []
    page = 1
    while True:
        url = f"{BASE_URL}/products/" if page == 1 else f"{BASE_URL}/products/page/{page}/"
        resp = get(url)
        if resp.status_code != 200:
            break
        for m in ITEM_PATTERN.finditer(resp.text):
            items.append({"url": m.group(2), "title": html.unescape(m.group(3)).strip()})
        page += 1
    return items


def build_record(item: dict, has_100g_twin: set[str]) -> dict | None:
    title = re.sub(r"\s+", " ", item["title"].replace("　", " ")).strip()
    if any(kw in title for kw in EXCLUDE_TITLE_KEYWORDS):
        return None
    resp = get(item["url"])
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {item['url']} ({resp.status_code})")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main")
    if main is None:
        return None
    text = main.get_text("\n", strip=True)
    k = text.find("商品カテゴリー")
    cat_text = text[k:k + 400] if k >= 0 else ""
    cat_text = re.split(r"商品タグ|商品ブランド", cat_text)[0]
    if not any(c in cat_text for c in BEAN_CATEGORIES):
        return None

    unit_m = UNIT_PATTERN.search(text)
    weight = int(unit_m.group(1)) if unit_m else None
    base = re.sub(r"\s*\(100g\)\s*$", "", title)
    if weight == 200 and base in has_100g_twin:
        return None  # 同一銘柄の100g版を代表にする
    name = base

    price = None
    in_stock = False
    form = soup.find("form", class_="variations_form")
    if form is not None and form.get("data-product_variations"):
        variations = json.loads(form["data-product_variations"])
        prices = [v["display_price"] for v in variations if v.get("display_price")]
        price = int(min(prices)) if prices else None
        in_stock = any(v.get("is_in_stock") and v.get("is_purchasable") for v in variations)

    # 説明: 商品仕様〜焙煎度一覧/販売価格の手前まで
    start = text.find("[商品") if "[商品" in text else (text.find("商品仕様") if "商品仕様" in text else 0)
    end_candidates = [i for i in (text.find("[焙煎度]"), text.find("\n" + title + "\n")) if i > start]
    end = min(end_candidates) if end_candidates else len(text)
    desc = re.sub(r"\s+", " ", text[start:end]).strip()[:400] or None

    parsed = parse_product(name)
    is_blend = "ブレンドコーヒー" in cat_text or "ブレンド" in name or "まかない" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, cat_text)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": "焙煎度はご注文時に選択(ご注文後に焙煎)",
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    items = list_items()
    twins = {re.sub(r"\s*\(100g\)\s*$", "", i["title"]).strip() for i in items if re.search(r"\(100g\)\s*$", i["title"])}
    records = []
    for item in items:
        try:
            rec = build_record(item, twins)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 取得失敗: {item['url']} ({e})")
            continue
        if rec is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mameiribito.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameiribito.json に出力しました")


if __name__ == "__main__":
    main()
