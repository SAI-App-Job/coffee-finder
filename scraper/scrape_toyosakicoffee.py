# -*- coding: utf-8 -*-
"""
scrape_toyosakicoffee.py

豊崎珈琲工場(琉球珊瑚珈琲。www.toyosakicoffeefactory.com、沖縄県豊見城市豊崎3-61。
運営: 沖縄上島珈琲株式会社)の商品情報を取得する。Wix(Wix Stores)。

【取得方法について】
実データ確認済み(2026-10時点): サイトマップ(store-products-sitemap.xml、全19商品)の
各商品ページ(/product-page/<slug>)に埋め込まれたJSON-LD(Product)から、商品名・説明・
価格(税込)・在庫(availability)を取得する。robots.txtは User-agent: * で Allow: /。

【対象商品について】
焙煎豆(全てブレンド)9商品: とよさきブレンド・まえじまブレンド(旧「冬のブレンド」、URLのslugは
冬のブレンド-200gのまま)・琉球珊瑚珈琲 ちゅらブレンド(Mild)/ちゅ〜ば〜ブレンド(Strong)/
じょ〜と〜ブレンド(Rich)・アイスブレンド 白(Shiru)/黒(Kuru)・コーヒーの日スペシャルブレンド2026
(期間限定 10/1〜10/15)・秋のブレンド2026(期間限定 10〜11月)。
除外: 飲み比べセット・3点セット・ギフトセット・ドリップバッグ(各種セット・ギフト含む)。
商品名の末尾の重量表記(150g。URLのslugの「200g」は旧表記)を採用する。
全てブレンドのため産地はnull(説明中の「原産国」「生豆生産国名」はflavor_notesに含まれる)。
焙煎度は記載が無い(苦味・酸味の★評価のみ)ためnull。
"""

import html
import json
import re
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "豊崎珈琲工場",
    "url": "https://www.toyosakicoffeefactory.com/",
    "platform": "Wix",
    "address": "沖縄県豊見城市豊崎3-61",
    "prefecture": "沖縄県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *はAllow: /。Disallow: *?lightbox=のみ)",
}

BASE_URL = "https://www.toyosakicoffeefactory.com"
SITEMAP_URL = f"{BASE_URL}/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ("セット", "ドリップ", "ギフト", "飲み比べ", "詰め合わせ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)


def get_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_product_ld(page_html: str) -> dict | None:
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def build_record(url: str, ld: dict) -> dict | None:
    raw_name = unicodedata.normalize("NFKC", html.unescape(ld.get("name") or "")).strip()
    raw_name = re.sub(r"\s+", " ", raw_name)
    if not raw_name or any(k in raw_name for k in NON_BEAN_KEYWORDS):
        return None
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = int(float(offers["price"])) if offers.get("price") else None
    in_stock = "InStock" in (offers.get("availability") or "")
    wm = WEIGHT_PATTERN.search(raw_name)
    weight_g = int(wm.group(1)) if wm else None

    desc = html.unescape(ld.get("description") or "")
    desc = desc.split("-----")[0]
    desc = re.sub(r"\s+", " ", desc).strip()[:400] or None

    display = re.sub(r"^《[^》]*》\s*", "", raw_name)
    display = re.sub(r"\s*\d+\s*g\s*$", "", display, flags=re.IGNORECASE).strip()
    parsed = parse_product(display)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": "ブレンド",
        "origin_country": None,
        "origin_source": None,
        "designated_brand": parsed["designated_brand"],
        "processing_method": None,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
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
    urls = re.findall(r"<loc>([^<]+)</loc>", get_text(SITEMAP_URL))
    records = []
    for url in urls:
        slug = urllib.parse.unquote(url.split("/product-page/")[-1])
        if any(k in slug for k in NON_BEAN_KEYWORDS):
            continue
        try:
            ld = parse_product_ld(get_text(url))
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {slug} ({e})")
            continue
        if not ld:
            print(f"[warn] JSON-LDなし: {slug}")
            continue
        rec = build_record(url, ld)
        if rec:
            records.append(rec)
        time.sleep(1)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_toyosakicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_toyosakicoffee.json に出力しました")


if __name__ == "__main__":
    main()
