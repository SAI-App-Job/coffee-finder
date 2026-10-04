# -*- coding: utf-8 -*-
"""
scrape_lupracoffee.py

喫茶ルプラ(lupra-coffee.shop-pro.jp、大阪市天王寺区上本町周辺の自家焙煎珈琲店・珈琲教室)の
商品情報を取得する。カラーミーショップ(shop-pro、charset=EUC-JP、`resp.encoding = "euc-jp"`を明示)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「珈琲豆 / COFFEE BEANS」(cbid=2945935、2ページ)の
銘柄(シングルオリジン・ブレンド・アイスブレンド)を対象とする。「焙煎豆メール便[送料無料]」
(複数銘柄のセット)、コーヒーバッグ(ドリップバッグ)、ギフト、体験(珈琲教室)は対象外。
HTTPのトップページはhttpsへのリダイレクトは発生せず、そのままhttpで取得できた(requests設定の
追加は不要)。

【価格・重量】
商品詳細ページの「オプションの詳細情報」表(状態×重量ごとの税込価格)から、豆のままの
最小重量(100g)の価格を採用する(全角表記「１００ｇ」はNFKC正規化して解析)。
【焙煎度】
商品名直下に「中深煎り　【フルシティロースト】」の形式で記載があり、roast_level/roast_hintに採用する。
【説明文】
詳細ページ下部の「About」本文のうち、区切り線(-----)より前の産地・栽培背景の説明を使う
(区切り線以降の「[ 商品名 ]」等のスペック表には別銘柄の内容が残っている商品があったため使わない)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "喫茶ルプラ",
    "url": "http://lupra-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "大阪府大阪市天王寺区",
    "prefecture": "大阪府",
    "robots_txt_status": "未確認",
}

BASE_URL = "http://lupra-coffee.shop-pro.jp"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2945935&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("メール便", "セット", "ギフト", "ドリップバッグ", "コーヒーバッグ", "体験", "教室")
MAX_PAGES = 5
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
FINE_ROASTS = {
    "ライト": "ライトロースト", "シナモン": "シナモンロースト", "ミディアム": "ミディアムロースト",
    "ハイ": "ハイロースト", "フルシティ": "フルシティロースト", "シティ": "シティロースト",
    "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, str] = {}
    for page in range(1, MAX_PAGES + 1):
        url = CATEGORY_URL + ("" if page == 1 else f"&page={page}")
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for li in soup.select("li.c-item-list__item"):
            a = li.select_one(".c-item-list__ttl a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            items[m.group(1)] = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if new == 0:
            break
    return [{"pid": pid, "name": name} for pid, name in items.items()]


def parse_weight_prices(soup: BeautifulSoup) -> list[tuple[int, int]]:
    """「オプションの詳細情報」表から(重量g, 税込価格)を取り出す(豆のままの行を優先)。"""
    rows = []
    for dl in soup.select("dl.p-price-table__dl"):
        state = dl.select_one("dt.p-price-table__dt")
        state_text = state.get_text(strip=True) if state else ""
        for li in dl.select("li.p-price-table-list__item"):
            name = li.select_one(".p-price-table-list__name")
            price = li.select_one(".p-price-table-list__price")
            if not (name and price):
                continue
            wm = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", name.get_text(strip=True)))
            pm = re.search(r"([\d,]+)\s*円", price.get_text())
            if wm and pm:
                grams = int(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)
                rows.append((state_text, grams, int(pm.group(1).replace(",", ""))))
    whole = [(g, p) for s, g, p in rows if s == "豆"]
    return whole or [(g, p) for s, g, p in rows]


def extract_description(soup: BeautifulSoup) -> str | None:
    body = soup.select_one("div.p-product-explain__body")
    if not body:
        return None
    text = body.get_text("\n", strip=True)
    text = re.split(r"-{5,}", text)[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400] or None


def build_record(item: dict) -> dict | None:
    url = f"{BASE_URL}/?pid={item['pid']}"
    soup = BeautifulSoup(fetch(url), "html.parser")
    title_el = soup.select_one("h2.p-product-info__ttl")
    title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)).strip() if title_el else item["name"]
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None

    wp = parse_weight_prices(soup)
    if not wp:
        price_el = soup.select_one(".p-product-price__sell")
        pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
        weight, price = None, (int(pm.group(1).replace(",", "")) if pm else None)
    else:
        weight, price = min(wp, key=lambda x: x[0])

    roast_el = soup.select_one("div.p-product-info__id")
    roast_text = (re.sub(r"\s+", " ", roast_el.get_text(" ", strip=True)).strip() if roast_el else "") or None
    roast_level = None
    if roast_text:
        m = COARSE_ROAST_PATTERN.search(roast_text)
        roast_level = m.group(1) if m else None
        fine = parse_product(roast_text)["roast_level"]
        if "ロースト" in roast_text and fine:
            roast_level = fine

    parsed = parse_product(title)
    if "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    page_text = soup.select_one("div.p-product").get_text(" ", strip=True) if soup.select_one("div.p-product") else ""
    out_of_stock = bool(re.search(r"SOLD\s*OUT|売り切れ|在庫なし|品切れ", page_text.split("About")[0]))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_text,
        "flavor_notes": extract_description(soup),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(k in item["name"] for k in EXCLUDE_KEYWORDS):
            continue
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_lupracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lupracoffee.json に出力しました")


if __name__ == "__main__":
    main()
