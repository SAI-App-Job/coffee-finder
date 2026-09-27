# -*- coding: utf-8 -*-
"""
scrape_cafecorazon.py

カフェ デ コラソン(cafecorazon.base.shop、京都府京都市上京区小川通一条上る
革堂町593-15、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
京都エリアの空白地調査(www.kitsune-coffee.com「京都のおすすめコーヒー豆
専門店15選」)で発見。

【対象商品について】
実データ確認済み(sitemap.xml全75件、2026-09時点): コーヒー豆17銘柄
(ベトナム・アラビカ、ペルー・エルパルゴマウンテン、エチオピア・シダモW、
スマトラ・マンデリン・タノバタック、ブラジル・ウォッシュト、マイルド
ブレンド、パナマ・ドンパチ・ティピカ、コスタリカ・ウエストバレー、
コロンビア・ウィラ、コロンビア・スプレモ、タンザニアAAアサンテ、
グァテマラSHB、コラソンブレンド、エチオピア・イルガチェフ、ケニアAA、
インディアAPAA、イタリアンブレンド)。各銘柄が受け取り方法別(【店頭受取】
【火曜配達便】【全国発送】)に最大3つの商品ページとして重複展開されている
ため、価格・重量が同一のこれらは「全国発送」版(焙煎度が併記されており
情報量が最も多い)を優先して1件に統合する。定期便専用サイズ(220g/300g等、
サブスクリプション限定SKU)・複数銘柄セット(お試しセット)・ドリップ
バッグ/パック類・雑貨(トートバッグ・ろ紙・ドリッパー等)・焼き菓子は
NON_BEAN_KEYWORDSで除外。

【商品説明について】
実データ確認済み: 全商品でog:description・meta descriptionともに空。
テイスティング等の記述は一切取得できないためflavor_notesはnullのまま
とする(存在しない情報を創作しない)。origin_country・roast_levelは
タイトル(「(浅煎り)」等の焙煎度・産地名の併記)から検出する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "カフェ デ コラソン",
    "url": "https://cafecorazon.base.shop/",
    "platform": "BASE",
    "address": "京都府京都市上京区小川通一条上る革堂町593-15",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://cafecorazon.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "キャロットケーキ", "水出し", "ドリップバッグ", "ドリップパック", "お試しコーヒーセット",
    "定期便", "トート", "ろ紙", "ドリッパー", "メジャースプーン", "スマートドリップフィルター",
    "フィナンシェ", "ヴァニレキプファルン", "レーズンサブレ", "ギフト箱",
]
BRACKET_PATTERN = re.compile(r"[【\[][^】\]]*[】\]]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup, url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    weight_m = WEIGHT_PATTERN.search(title)
    return {"url": url, "title": title, "price": price, "weight_g": int(weight_m.group(1)) if weight_m else None}


def dedupe_by_fulfillment(items: list[dict]) -> list[dict]:
    """受け取り方法(店頭受取/火曜配達便/全国発送)違いの重複を統合する。
    理由はモジュールdocstring参照。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = BRACKET_PATTERN.sub("", item["title"])
        base = re.sub(r"[（(][^）)]*[）)]", "", base)  # 焙煎度の注記(浅煎り等)を除去
        base = WEIGHT_PATTERN.sub("", base)
        base = re.sub(r"[\s　]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        preferred = next((x for x in group if "全国発送" in x["title"]), group[0])
        result.append(preferred)
    return result


def build_record(item: dict) -> dict | None:
    title = BRACKET_PATTERN.sub("", item["title"]).strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": item["title"],
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    parsed = apply_category_hint_fallback(parsed, title)
    stock_status = detect_stock_status(item["title"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": item["title"],
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"] or 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    prelim = []
    for url in item_urls:
        try:
            soup = fetch(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        fields = extract_fields(soup, url)
        if fields:
            prelim.append(fields)

    deduped = dedupe_by_fulfillment(prelim)

    records = []
    flavored_records = []
    for item in deduped:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cafecorazon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafecorazon.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
