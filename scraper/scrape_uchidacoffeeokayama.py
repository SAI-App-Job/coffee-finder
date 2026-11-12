# -*- coding: utf-8 -*-
"""
scrape_uchidacoffeeokayama.py

UCHIDA COFFEE(https://uchida.coffee/、岡山県岡山市北区中島田町1-2-2。岡山店・津山店の2店)の
商品情報を取得する。WordPress + WooCommerce(Store API /wp-json/wc/store/v1/products)。
(静岡の内田珈琲 scrape_uchidacoffee.py とは別店。slugを分けている。)

【対象商品について】
実データ確認済み(2026-11-02): Store APIの全6件のうち、ドリップバッグ(simple商品)1件を除く
コーヒー豆5銘柄(ストレート4・デカフェ1)を対象とする。ブレンドの取り扱いは現時点でない。
サイトは2026-04にオンラインストアを開設したばかりで商品数は少ない。

【重量・価格】
各商品とも「150g / 300g / 450g」のサイズ展開で、商品名・Store APIの価格は最小の150g分
(挽き方バリエーションの「豆のまま」も同価格)。商品名末尾の「150g」から重量を取得する。
焙煎度・精製・産地は説明文末尾の Information 欄(Origin / Process / Roast Level)から取得する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "UCHIDA COFFEE",
    "url": "https://uchida.coffee/",
    "platform": "WordPress + WooCommerce",
    "address": "岡山県岡山市北区中島田町1-2-2",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-11-02確認。User-agent: * は Allow: / で、/wp-json/ は禁止されていない。Disallowは管理画面・WooCommerceログ等と ?add-to-cart= のみ。Content-Signalは search=yes, ai-train=no, use=reference。ClaudeBot等のAI学習クローラは名指しで禁止だが、本スクリプトは識別UA CoffeeFinderBot を使用)",
    "source_note": "WooCommerce Store API(https://uchida.coffee/wp-json/wc/store/v1/products)と各商品ページ、特商法ページ(/legal/)を2026-11-02に確認。2026-04にオンラインストア開設、最新お知らせ2026-10-21。価格は最小サイズの150g。店舗は岡山店・津山店の2店(住所は特商法記載の岡山店)",
    "last_verified_at": "2026-11-02",
}

API_URL = "https://uchida.coffee/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
PROCESS_MAP = [
    ("mosto anaerobic", "アナエロビック(モスト)"),
    ("pulped natural", "パルプドナチュラル"),
    ("washed", "ウォッシュド"),
    ("natural", "ナチュラル"),
    ("honey", "ハニー"),
]
COUNTRY_JA = {"Ethiopia": "エチオピア", "Guatemala": "グアテマラ", "Brazil": "ブラジル", "Mexico": "メキシコ"}


def info_field(desc_text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+)$", desc_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def build_record(p: dict) -> dict | None:
    name_raw = html.unescape(p["name"]).strip()
    cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
    if p.get("type") != "variable" or "ドリップバッグ" in cats or re.search(r"drip\s*bag", name_raw, re.I):
        return None
    wm = re.search(r"\s(\d+)\s*g$", name_raw)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"\s+(\d+)\s*g$", "", name_raw).strip()

    desc_text = BeautifulSoup(p.get("description") or "", "html.parser").get_text("\n", strip=True)
    short = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text("\n", strip=True)
    flavor = short.split("\n")[0].strip() if short else None
    tn = re.search(r"Tasting Notes:\s*\n?(.+)", short)
    flavor_notes = " ".join(x for x in [flavor, ("Tasting Notes: " + tn.group(1).strip()) if tn else None] if x)[:400] or None

    parsed = parse_product(name)
    parsed["category"] = "ストレート"
    parsed = apply_category_hint_fallback(parsed, name)
    origin_en = info_field(desc_text, "Origin")
    if origin_en in COUNTRY_JA:
        parsed["origin_country"] = COUNTRY_JA[origin_en]
        parsed["origin_source"] = "description"

    process_en = (info_field(desc_text, "Process") or "")
    decaf = "decaf" in name.lower() or "Decaf" in process_en or any("カフェインレス" in c for c in cats)
    processing = None
    if not decaf:
        for key, ja in PROCESS_MAP:
            if key in process_en.lower():
                processing = ja
                break
    rm = re.search(r"Roast Level:.*?\((\S+?)\)", desc_text)
    roast_level = rm.group(1) if rm else None

    farm = info_field(desc_text, "Farm")
    region = info_field(desc_text, "Region")
    producer = info_field(desc_text, "Producer")
    farm_note = " / ".join(x for x in [f"Region: {region}" if region else None,
                                       f"Farm: {farm}" if farm else None,
                                       f"Producer: {producer}" if producer else None] if x) or None

    price_info = p.get("prices") or {}
    price = int(price_info["price"]) if price_info.get("price") else None
    in_stock = bool(p.get("is_in_stock"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing or (None if decaf else parsed["processing_method"]),
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "decaf_process": "マウンテンウォータープロセスによりカフェインを除去" if decaf and "Mountain Water" in process_en else None,
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def main():
    resp = requests.get(API_URL, params={"per_page": 100}, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    records = [r for r in (build_record(p) for p in resp.json()) if r]
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_uchidacoffeeokayama.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_uchidacoffeeokayama.json に出力しました")


if __name__ == "__main__":
    main()
