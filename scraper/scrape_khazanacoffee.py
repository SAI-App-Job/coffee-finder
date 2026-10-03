# -*- coding: utf-8 -*-
"""
scrape_khazanacoffee.py

カザーナコーヒー(khazana-coffee.com、東京都八王子市本町2-5 1F。2022年開業の
スペシャルティコーヒー自家焙煎店。イオン八王子滝山の「Khazana Coffee in Lots」と
合わせて2店舗)の商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`から全商品ページURLを列挙し、
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を取得する。
価格は「100gごとに￥1,280」(100g単位の従量販売)のため、代表重量は100g、価格は
JSON-LDの価格とする(ページ内の「<数字>gごとに」表記から重量を取得)。
豆の状態(豆のまま/挽く)はオプション選択のため豆として扱う。焙煎度は
カラースウォッチのオプションでテキストが無いため商品名に明記がある場合のみ取得する。

【対象商品について】
ドリップバッグ・ギフトBox/ギフトセット・エスプレッソシロップ・器具(ミル・タンブラー・
ボトル・コーヒーバネット)・トートバッグは除外する。「Op.1」〜「Op.8」「Khazana Blend」
「八王子ブレンド」「高尾山ブレンド」「秋ブレンド」等のブレンドはcategory「ブレンド」とする。
"""

import html
import json
import re
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "カザーナコーヒー",
    "url": "https://www.khazana-coffee.com/",
    "platform": "Wix(Wix Stores)",
    "address": "東京都八王子市本町2-5 1F",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.khazana-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
EXCLUDE_KEYWORDS = (
    "ドリップバッグ", "ドリップパック", "ギフト", "gift", "シロップ", "ceramug", "grinder", "グラインダー",
    "zassenhaus", "バネット", "トートバッグ", "fellow", "ボトル", "タンブラー",
)
BLEND_NAME_PATTERN = re.compile(r"(Op\.\s*\d+|blend|ブレンド)", re.I)

# 国名が商品名に含まれるが表記ゆれで検出されないもの
COUNTRY_FALLBACKS = {"ホンデュラス": "ホンジュラス"}


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def clean_name(text: str) -> str:
    text = html.unescape(text)
    text = text.replace('"', "").replace("”", "").replace("“", "")
    return re.sub(r"\s+", " ", text).strip()


def build_record(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))
    name = clean_name(ld.get("name", ""))
    if any(kw.lower() in name.lower() or kw.lower() in unquote(url).lower() for kw in EXCLUDE_KEYWORDS):
        return None

    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()[:500] or None
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    page_text = html.unescape(re.sub(r"<[^>]+>", " ", resp.text))
    weight_m = re.search(r"(\d+)\s*g(?:（グラム）)?\s*ごとに", page_text)
    weight_g = int(weight_m.group(1)) if weight_m else None

    parsed = parse_product(name)
    if BLEND_NAME_PATTERN.search(name):
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            for kw, country in COUNTRY_FALLBACKS.items():
                if kw in name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "country_name"
                    break
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

    # 精選方法: 本文中の「Processing :」行(例: Washed / Natural)
    processing = parsed["processing_method"] or detect_processing_method(name)
    if not processing:
        pm = re.search(r"Processing\s*[:：]\s*([A-Za-z][A-Za-z ]*)", re.sub(r"\s+", " ", page_text))
        if pm:
            processing = detect_processing_method(pm.group(1))

    # 焙煎度: 「Roast Level：...（浅煎り）」が1種類のみ記載されている場合に限り採用
    roast = parsed["roast_level"]
    if not roast:
        levels = set(re.findall(r"Roast Level[:：][^（]{0,40}（([^）]*煎り)）", re.sub(r"\s+", " ", page_text)))
        if len(levels) == 1:
            roast = levels.pop()
    roast_hint = None
    if roast and "+" in roast:  # 複数ローストの配合(ブレンド)は焙煎度ではなくヒントとして保持
        roast_hint, roast = roast, None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            record = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {url} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_khazanacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_khazanacoffee.json に出力しました")


if __name__ == "__main__":
    main()
