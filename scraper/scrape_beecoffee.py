# -*- coding: utf-8 -*-
"""
scrape_beecoffee.py

Bee Coffee(ビー コーヒー、bee-coffee.com、東京都八王子市散田町3-19-23、西八王子駅南口
徒歩3分、2014年設立の自家焙煎珈琲豆専門店、単独1店舗)の商品情報を取得する。
公式サイト(HTML+独自CGIカート)の通信販売ページはBASE(beecoffee.base.shop)で、
商品ごとの個別URL・在庫表示があるためこちらを取得元とする。
なお「ビーズコーヒー」(beescoffeeshop.shop-pro.jp、scrape_beescoffee.py)は別店舗。

【商品について】
実データ確認済み(2026-10時点): sitemap.xmlの/items/配下60件のうち、「(200g)」付きの
珈琲豆(ブレンド5・ストレート25前後)のみを対象とする。ドリップバッグ(5袋)・水出し
珈琲バッグ・商品グループ見出し(「珈琲豆 ブレンド ￥1,420～」等のバリエーション親)・
「_」名の個別注文用商品は除外する。
価格は「生豆200gの煎り上がり価格」(焙煎後は160〜180g)で、商品名の「(200g)」と
同一基準のため、代表重量は200g(生豆換算)とする。豆/粉のバリエーションは
豆のままの価格と同一。在庫は購入ボタンの在庫なし(itemUnavailable)で判定する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Bee Coffee(ビー コーヒー)",
    "url": "https://bee-coffee.com/",
    "platform": "BASE(公式サイトは独自CGIカート)",
    "address": "東京都八王子市散田町3-19-23",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(BASE系店舗共通の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://beecoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

WEIGHT_PATTERN = re.compile(r"[(（]\s*(\d+)\s*[gｇ]\s*[)）]")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def list_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return [u for u in re.findall(r"<loc>([^<]+)</loc>", resp.text) if "/items/" in u]


def build_record(url: str) -> dict | None:
    soup, raw_html = fetch_soup(url)
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    m = WEIGHT_PATTERN.search(title)
    if not m:  # ドリップバッグ(5袋)・水出しバッグ・親見出し等
        return None
    weight_g = int(m.group(1))
    name = unicodedata.normalize("NFKC", WEIGHT_PATTERN.sub("", title))
    name = re.sub(r"\s+", " ", name).strip()

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    desc = re.sub(r"\s+", " ", desc_el["content"]).strip()[:500] if desc_el and desc_el.get("content") else None
    out_of_stock = 'id="itemUnavailable" value="1"' in raw_html

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    elif not parsed["origin_country"]:
        detected = detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

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
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_item_urls():
        try:
            record = build_record(url)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {url} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beecoffee.json に出力しました")


if __name__ == "__main__":
    main()
