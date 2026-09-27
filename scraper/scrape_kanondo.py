# -*- coding: utf-8 -*-
"""
scrape_kanondo.py

Coffee Base KANONDO(kanondo.theshop.jp、京都府京都市中京区観音堂町466、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(theshop.jp、
thebase.inと同一エンジン)。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp等)で発見。公式サイトが案内する
主要オンラインストア(shop.kanondo.coffee、Shopify)はこの環境からTLS
接続に失敗する(python-requests/curl/ブラウザいずれも接続不可)。同店が
運営する別プラットフォーム版(kanondo.theshop.jp、BASE)が正常にアクセス
でき、Coffee Beansカテゴリの在庫も現行のものと確認できたためこちらを
情報源として採用する。梨木神社境内のCoffee Base NASHINOKIも同一
オンラインストアを共有(2拠点)。

【対象商品の判別方法について】
実データ確認済み(sitemap.xml全72件、2026-09時点): 商品名が「コーヒー豆 」
で始まる商品のみを対象とする(ドリップバッグ・アイスコーヒーバッグ・
自家焙煎アーモンド・雑貨・アパレル・抽出器具等、他の非対象商品は
この接頭辞を持たないため、キーワード除外リストより高精度に判別できる)。
「オリジナル サニー/ダーク ブレンド」は商品名に重量表記が無く実体は
ドリップバッグ(単価194円で他のドリップバッグと同額)のため、この判別
方法により自動的に除外される。対象12銘柄(ストレート10・ブレンド2)×
100g/200g/300gの重複は最小重量側のみ採用する。

【商品説明について】
実データ確認済み: og:descriptionに産地・精製方法・焙煎度+テイスティング
文が含まれるが、末尾に「酸味ーーーー★苦味キレーー★ーーコク」という
星取り表(視覚的なバー表現でテキストとしては意味を持たない)が付随する
ため正規表現で除去する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "Coffee Base KANONDO",
    "url": "https://www.kanondo.coffee/",
    "platform": "BASE(theshop.jp)",
    "address": "京都府京都市中京区観音堂町466",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://kanondo.theshop.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
STRIP_WEIGHT_PATTERN = re.compile(r"\s*\d+\s*[gｇ]\s*")
RATING_BAR_PATTERN = re.compile(r"酸味[ー\-]*★?[ー\-]*苦味.*?コク")


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
    if not title.startswith("コーヒー豆 ") or "麻袋" in title:
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    desc = desc_el["content"] if desc_el and desc_el.get("content") else ""
    desc = RATING_BAR_PATTERN.sub("", desc)
    desc = re.split(r"賞味期限", desc)[0].strip()

    weight_m = WEIGHT_PATTERN.search(title)
    return {"url": url, "title": title, "price": price, "flavor_notes": desc or None,
            "weight_g": int(weight_m.group(1)) if weight_m else None}


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_WEIGHT_PATTERN.sub("", item["title"])
        base = re.sub(r"[\s　]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def build_record(item: dict) -> dict | None:
    title = re.sub(r"^コーヒー豆\s*", "", item["title"])
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

    detected = detect_country_name(title) or (item["flavor_notes"] and detect_country_name(item["flavor_notes"]))
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if item["flavor_notes"]:
        m = re.search(r"(ウォッシュド|ナチュラル|ハニー|パルプドナチュラル|アナエロビック)", item["flavor_notes"])
        if m:
            parsed["processing_method"] = normalize_processing_method(m.group(1))

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
        "flavor_notes": item["flavor_notes"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
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

    deduped = dedupe_by_base_name(prelim)

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
    with open("data_kanondo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kanondo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
