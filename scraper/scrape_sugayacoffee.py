# -*- coding: utf-8 -*-
"""
scrape_sugayacoffee.py

SugayaCoffee(スガヤコーヒー、sugayacoffee.ocnk.net、茨城県つくば市春日4-24-19)の
商品情報を取得する。おちゃのこネット(Ocnk)クリーンURLテーマ(あさみ珈琲豆店と同系統)。

robots.txt確認済み(2026-10時点): GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ
Disallow: /、それ以外は制限なし。

【商品一覧】sitemap.xmlの`/product/N`形式(38件)を起点とする。
【除外】ドリップバッグ・各種「セット」・ギフト・水出しバッグ(NON_BEAN_KEYWORDS)。
【重量】商品名には重量が無く、詳細説明冒頭の「［２００ｇサイズ］」または
「500g」表記から取得(NFKC正規化)。同一銘柄が200g/500gで別商品のため、
基準名(商品名)でグルーピングして最小重量(200g)を代表とする。
【価格】`product:price:amount`はサイト表記の税込価格(例: 200g 1,800円(税別)→1,944円)。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "SugayaCoffee",
    "url": "https://sugayacoffee.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "茨城県つくば市春日4-24-19",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-10確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://sugayacoffee.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "セット", "ギフト", "水出し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"［味わい］|\[味わい\]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc")
            if re.search(r"/product/\d+$", loc.get_text(strip=True))]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    og = soup.select_one('meta[property="og:title"]')
    if not og or not og.get("content"):
        return None
    title = unicodedata.normalize("NFKC", og["content"]).strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one("div.item_desc_text")
    desc = unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)) if desc_el else ""
    wm = WEIGHT_PATTERN.search(desc)
    weight = int(wm.group(1)) if wm else None
    # 説明冒頭(商品名・サイズ表記の後、［味わい］の前)をflavor_notesとする
    head = FLAVOR_STOP_PATTERN.split(unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)))[0] if desc_el else ""
    head = re.sub(r"^" + re.escape(title), "", head).strip()
    head = re.sub(r"\[\d+g[^\]]*\]", "", head).strip()
    head = re.sub(r"\s+", " ", head).strip() or None
    rm = re.search(r"焙煎\s*[:：]\s*([^\s]+?)(?:のブレンド)?(?:\s|$)", desc)
    roast = rm.group(1) if rm else None
    page_text = soup.get_text(" ", strip=True)
    sold_out = bool(re.search(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ", page_text))
    return {"title": title, "price": price, "weight": weight,
            "flavor_notes": head, "sold_out": sold_out,
            "raw_name": " ".join(x for x in [title, f"{weight}g" if weight else None, roast] if x)}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_name: dict[str, dict] = {}
    for item in items:
        key = re.sub(r"\s+", " ", item["title"]).strip()
        ex = by_name.get(key)
        w = item["weight"] if item["weight"] else float("inf")
        exw = (ex["weight"] if ex and ex["weight"] else float("inf"))
        if ex is None or w < exw:
            by_name[key] = item
    return list(by_name.values())


def build_record(item: dict) -> dict:
    title = item["title"]
    raw_name = item["raw_name"]
    parsed = parse_product(raw_name)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"], "raw_name": raw_name,
            "category": "フレーバー", "is_flavored": True,
            "flavor_name": parsed["flavor_name"], "price": item["price"],
            "product_url": item["url"],
        }
    stock_status = "品切れ" if item["sold_out"] else detect_stock_status(title)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    for url in fetch_product_urls():
        try:
            f = extract_fields(fetch_page(url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not f or any(kw in f["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        f["url"] = url
        all_items.append(f)

    previous = load_previous_products(SHOP_INFO["name"])
    records, flavored = [], []
    for item in pick_canonical_items(all_items):
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue
        d = build_record(item)
        (flavored if d.get("is_flavored") else records).append(d)
    return records, flavored


if __name__ == "__main__":
    import json

    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": flavored}
    with open("data_sugayacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sugayacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored)}件は別枠に分離)")
