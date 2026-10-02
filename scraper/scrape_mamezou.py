# -*- coding: utf-8 -*-
"""
scrape_mamezou.py

自家焙煎珈琲工房まめぞう(www.mamezou.co.jp、埼玉県戸田市上戸田5-11-1)の
商品情報を取得する。独自CMSのショッピング機能(2025年4月にクレジットカード
決済対応)。豆50種類以上を自家焙煎。

【店舗発見の経緯】
2026-09-04の別セッションで「独自ショッピング機能の構造調査に時間を要する」
として見送られていたが、全国再調査(埼玉県)で再検証し、plain requestsで
全商品が取得できることを確認して実装した。

【対象商品について】
実データ確認済み(2026-10時点): ショップ一覧(/shop/)の全40商品のうち、
ドリップパックコーヒー(ギフト・30個等の5商品)を除いた35商品を対象とする。
価格は一覧の`data-price`(カート価格)を採用する。商品詳細ページには説明文が
無いため、説明文は各カテゴリページ(中南米・アジア/カリブ海・アフリカ・
ブレンド/カフェインレス)の商品紹介文から商品名の一致で補完する。
カテゴリページは全て「価格は250g表示です」と明記されているため重量は250g。

【分類について】
ブレンド・カフェインレス・アイスコーヒー用の商品は商品名に「ブレンド」が
無いものがあるため(例:「琥珀のアイスコーヒー」)、ブレンド/カフェインレス
ページに掲載され国名が判定できない商品はブレンドとして扱う。ただし
「カフェインレス」を含む商品は産地別の単一銘柄なのでストレートのままとする。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲工房 まめぞう",
    "url": "https://www.mamezou.co.jp/",
    "platform": "独自CMSショップ",
    "address": "埼玉県戸田市上戸田5-11-1",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.mamezou.co.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

CATEGORY_PAGES = ["chunanbei.html", "carib.html", "africa.html", "other.html"]
ITEM_PATTERN = re.compile(r'data-number="(\d+)" data-name="([^"]*)"[^>]*data-price="(\d+)"')


def normalize(text: str) -> str:
    return re.sub(r"[\s・･,、.]", "", unicodedata.normalize("NFKC", text))


def load_descriptions() -> dict[str, tuple[str, str]]:
    """正規化した商品名 -> (説明文, 掲載ページ)"""
    result: dict[str, tuple[str, str]] = {}
    for page in CATEGORY_PAGES:
        resp = requests.get(f"{BASE_URL}/{page}", headers=REQUEST_HEADERS, timeout=20)
        resp.encoding = "utf-8"
        text = BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True)
        for chunk in text.split("ご購入はこちら"):
            lines = [ln for ln in chunk.split("\n") if ln.strip()]
            weight_idx = next((i for i, ln in enumerate(lines) if "250g表示" in ln), None)
            if weight_idx is None:
                continue
            # 重量行より前で、商品名らしい行(後で一覧と突き合わせる)を全て候補にする
            for j in range(weight_idx):
                desc_lines = [ln for ln in lines[j + 1:weight_idx] if not ln.startswith("（SOLD")]
                result.setdefault(normalize(lines[j]), (" ".join(desc_lines), page))
    return result


def build_records() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/shop/", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    items = ITEM_PATTERN.findall(resp.text)
    descriptions = load_descriptions()

    records = []
    for number, name, price in items:
        if "ドリップパック" in name:
            continue
        key = normalize(name)
        desc, page = descriptions.get(key, (None, None))
        if page is None:
            # 一覧の商品名がカテゴリページの名称に生産者名等を付加した形の場合は前方一致で補完
            for cand, value in descriptions.items():
                if len(cand) >= 8 and (key.startswith(cand) or cand.startswith(key)):
                    desc, page = value
                    break

        parsed = parse_product(name)
        if parsed["category"] != "ブレンド":
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if (
                page == "other.html"
                and not parsed["origin_country"]
                and "カフェインレス" not in name
            ):
                parsed["category"] = "ブレンド"
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(price),
            "weight_g": 250,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{BASE_URL}/shop/detail.html?category=&item_number={number}",
        })
    return records


def main():
    records = build_records()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamezou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamezou.json に出力しました")


if __name__ == "__main__":
    main()
