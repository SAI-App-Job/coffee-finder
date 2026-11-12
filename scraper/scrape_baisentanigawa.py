# -*- coding: utf-8 -*-
"""
scrape_baisentanigawa.py

焙煎たにがわ(北海道札幌市西区発寒5条8丁目12-3、楽々シリーズ/Raku-Uru の
tani.raku-uru.jp)の商品情報を取得する。公式サイトは tani.co.jp、実店舗あり。

【プラットフォーム】
商品一覧(/item-list、ページネーションなし・全9件)と商品詳細(/item-detail/<id>)は
サーバーサイドレンダリングの静的HTML。商品詳細の `variationId` ラジオ
(「豆100g」「豆200g」「粉100g」「粉200g」)は初期選択が「豆100g」で、
`b.raku-item-vari-price-num` に表示される価格がその豆100gの税込価格。
本文(説明文)・産地表記は無いため、産地は商品名から判定する。
在庫は `a.raku-add-cart`(カートボタン)の有無で判定する。

【対象】
コーヒー豆7件(ストレート6・デカフェ1)。HARIOペーパー(器具)と
「3種類飲み比べセット」は除外。商品名先頭の「深煎り」「浅煎り」「中深煎り」は焙煎度。

robots.txt: /robots.txt は HTTP 404(自前の404ページ)で存在せず、明示的な制限なし。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "焙煎たにがわ",
    "url": "http://tani.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "北海道札幌市西区発寒5条8丁目12-3",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-10-26確認。/robots.txtはHTTP 404で存在せず、明示的なDisallow指定が無い)",
    "source_note": "Raku-Uru公式ショップ(http://tani.raku-uru.jp/ 、/item-list、/item-detail/*)を2026-10-26に確認。"
                   "特定商取引法ページ(/law)に〒063-0825 札幌市西区発寒5条8丁目12-3、公式 https://tani.co.jp/ に「札幌でコーヒー豆を焙煎・販売しています」。"
                   "豆のまま100gの価格を採用(一部商品は商品ページの初期表示が粉100gだが豆・粉共通価格)。ショップ内のお知らせは2021年の1件のみで商品の更新日は不明。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "http://tani.raku-uru.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 2
NON_BEAN_KEYWORDS = ("ペーパー", "セット", "飲み比べ", "ドリップバッグ")
ORIGIN_OVERRIDES = {"ガテマラ": "グアテマラ", "東チモール": "東ティモール"}
ROAST_PREFIXES = ("中深煎り", "深煎り", "中煎り", "浅煎り")
ROAST_MAP = {"深煎り": "深煎り", "中深煎り": "中深煎り", "中煎り": "中煎り", "浅煎り": "浅煎り"}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    raw = resp.content
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp932", errors="replace")
    return BeautifulSoup(text, "html.parser")


def list_item_urls() -> list[str]:
    soup = fetch_soup(f"{BASE_URL}/item-list")
    urls = []
    for a in soup.select('a[href^="/item-detail/"]'):
        u = BASE_URL + a["href"]
        if u not in urls:
            urls.append(u)
    return urls


def build_record(url: str) -> dict | None:
    soup = fetch_soup(url)
    h1 = soup.select_one("h1.ttl")
    if not h1:
        return None
    title = h1.get_text(strip=True)
    if any(k in title for k in NON_BEAN_KEYWORDS):
        return None

    price = None
    price_el = soup.select_one("b.raku-item-vari-price-num")
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    # 重量: 「豆」バリエーション(「豆100g」「100g豆」の両表記)の最小重量。
    # 一部商品は初期選択が「100g粉」だが、一覧の価格は豆・粉共通で変わらないため、その表示価格を採用する。
    weights = []
    for lab in soup.select("div.item-detail-radio label"):
        text = lab.get_text(strip=True)
        wm = re.search(r"(\d+)\s*g", text)
        if wm and "豆" in text and "粉" not in text:
            weights.append(int(wm.group(1)))
    weight = min(weights) if weights else None

    roast = next((ROAST_MAP[p] for p in ROAST_PREFIXES if title.startswith(p)), None)
    name = title
    for k, v in ORIGIN_OVERRIDES.items():
        name = name.replace(k, v)
    parsed = parse_product(name)
    detected = detect_country_name(name)
    if detected and not parsed["origin_country"]:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, name)
    if "デカフェ" in name:
        parsed["category"] = parsed["category"] or "デカフェ"

    in_stock = soup.select_one("a.raku-add-cart") is not None
    stock_status = detect_stock_status(title, not in_stock)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "flavor_notes": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for u in list_item_urls():
        time.sleep(CRAWL_DELAY_SECONDS)
        rec = build_record(u)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    if not records:
        print("[warn] 商品0件のため出力しません")
        return
    with open("data_baisentanigawa.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisentanigawa.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
