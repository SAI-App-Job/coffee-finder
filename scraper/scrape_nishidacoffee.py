# -*- coding: utf-8 -*-
"""
scrape_nishidacoffee.py

Nishida Coffee(にしだコーヒー、nishidacff.thebase.in、山口県山口市湯田温泉
五丁目7-6、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【住所について】
公式ストアの特定商取引法ページ(https://nishidacff.thebase.in/law)で実データ
確認済み(2026-09時点): 「事業者の所在地　〒753-0056 山口県山口市湯田温泉
五丁目7-6」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【商品名の記号について】
実データ確認済み(2026-09時点、全35件): 銘柄名は「-狐-（こぎつね珈琲）」
「-読-　Nishida Blend（ニシダブレンド）」のように「-記号-（説明）」の形式。
記号自体はブレンド名の一部であり除去しない(coffee_parserは括弧内の説明文から
産地・ブレンド判定を行う)。

【重量について】
実データ確認済み: 通常のレギュラーコーヒー商品(狐・読・麗・恋・学・憩・凛・陽・
京、および文豪シリーズの2品)はいずれも商品名に重量表記が無いが、商品説明文の
「内容量 100g」ラベルで統一されていることを実データで確認した(例: -狐-の説明文)。
weight_gが商品名から取得できない場合は説明文の「内容量」ラベルから取得し、
それも無ければFIXED_WEIGHT_G=100を採用する。

【非コーヒー豆商品の除外について】
実データ確認済み(全35件): ドリップバッグ単品・詰め合わせ・定期便(「毎月お届け」
表記、ブレンド名を「＆」で複数連結)、水出しコーヒーバッグ、こぎつねバウム(菓子)、
番茶珈琲(コーヒーではなく番茶)、コーヒー豆詰め合わせセット各種、コーヒー
スプーン・ポット・ノート・コーヒー風呂(雑貨)が非対象。NON_BEAN_KEYWORDSで
除外する。残り11件(-狐-,-読-,-麗-,-恋-,-学-,-憩-,-凛-,-陽-,-京-、
種田山頭火・旅路Blend、中原中也・帰郷Blendの計11銘柄)を対象とする。

【原産国について】
実データ確認済み: 商品名の記号だけでは産地が分からないため、商品説明文の
「原材料 コーヒー豆(原産国：X、Y)」ラベルからcoffee_parser.detect_country_name()
で検出する(単一国ならストレート、複数国ならブレンド扱いでorigin_countryは
Noneのまま産地情報はflavor_notesに残す方針は取らず、ラベルどおりの表記を
origin_country検出に用いる)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, detect_country_name

SHOP_INFO = {
    "name": "Nishida Coffee",
    "url": "https://nishidacff.thebase.in/",
    "platform": "BASE",
    "address": "山口県山口市湯田温泉五丁目7-6",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://nishidacff.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照。実データ確認済み(2026-09時点)の非豆商品を網羅
NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "ドリップパック", "水出し", "バウム", "番茶", "セット",
    "スプーン", "ポット", "ノート", "コーヒー風呂", "毎月お届け", "＆",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ORIGIN_LABEL_PATTERN = re.compile(r"原産国[：:]\s*([^\n)）]+)")
CONTENT_LABEL_PATTERN = re.compile(r"内容量\s*\n?\s*(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 100  # 理由はモジュールdocstring参照


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].split(" powered by BASE")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    body_text = soup.get_text("\n")

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

    # 記号だけの商品名からは産地を検出できないため、説明文の「原産国：」ラベルを使う
    origin_match = ORIGIN_LABEL_PATTERN.search(body_text)
    if origin_match and parsed["origin_country"] is None:
        country = detect_country_name(origin_match.group(1))
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    weight_m = WEIGHT_PATTERN.search(title)
    if weight_m:
        weight_g = int(weight_m.group(1))
    else:
        content_m = CONTENT_LABEL_PATTERN.search(body_text)
        weight_g = int(content_m.group(1)) if content_m else FIXED_WEIGHT_G

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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for item_url in item_urls:
        try:
            detail = build_record(fetch_page(item_url), item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
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
    with open("data_nishidacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishidacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
