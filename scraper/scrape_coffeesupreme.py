# -*- coding: utf-8 -*-
"""
scrape_coffeesupreme.py

Coffee Supreme Tokyo(shopjp.coffeesupreme.com、東京都渋谷区神山町42-3、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(独自ドメイン運用、
URLパターン/items/<id>がthebase.in系と同一のため実データ確認済み)。

【店舗発見の経緯】
高田馬場エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、渋谷
エリアを調査した際に発見。1993年ニュージーランド・ウェリントン発、2017年に
渋谷へ上陸したスペシャルティコーヒーロースターカンパニー。日本国内は渋谷店・
本所ロースタリー(墨田区)の2拠点のみで、海外(NZ・豪州)の店舗数を含めても
本プロジェクトの「11店舗以上のチェーンは対象外」基準には該当しないと判断
した(FUGLEN TOKYO等、海外発で日本国内の店舗数が少ない既収録店と同じ扱い)。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「コーヒー豆」サブカテゴリ(/categories/3788465、
14件)を対象とする。「COFFEEを探す」上位カテゴリ全体(24件)には「ドリップ
バッグ」「インスタント」等が混在するため、より対象が絞られたサブカテゴリを
採用した。「Coffee Supreme インスタントコーヒー」はインスタントのため
NON_BEAN_KEYWORDSで除外。バンドコラボ商品(Dinosaur Jr・American Football・
The Beths)は特別パッケージなだけで実体は自家焙煎豆のため対象に含める。

【150g/1kg重複について】
実データ確認済み: 「ハウスブレンド　Supreme Blend」「TOKYO ブレンド」の
2銘柄が150g/1kgを別商品ページとして展開している。OBSCURA COFFEE
ROASTERSと同じ方針で、重量表記を除いた銘柄名が一致する場合は最小重量側の
みを採用する。

【flavor_notes】
実データ確認済み: og:descriptionに日本語のテイスティング文+英語の
Flavour/Aroma/Acidity/Body/Finish各項目が無関係な定型文の混入無く
含まれているため全文をそのまま採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Coffee Supreme Tokyo",
    "url": "https://shopjp.coffeesupreme.com/",
    "platform": "BASE(独自ドメイン運用)",
    "address": "東京都渋谷区神山町42-3",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://shopjp.coffeesupreme.com"
CATEGORY_URL = f"{BASE_URL}/categories/3788465"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["インスタントコーヒー", "ドリップバッグ", "ドリップ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]|(\d+)\s*kg", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"\s*(\d+\s*[gｇ]\s*[〜~]?|\d+\s*kg)\s*", re.IGNORECASE)


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch(CATEGORY_URL)
    urls = []
    seen = set()
    for a in soup.select('a[href*="/items/"]'):
        m = re.search(r"/items/(\d+)", a.get("href", ""))
        if not m:
            continue
        url = f"{BASE_URL}/items/{m.group(1)}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_weight_g(title: str) -> int | None:
    m = re.search(r"(\d+)\s*kg", title, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", title)
    return int(m.group(1)) if m else None


def fetch_fields(url: str) -> dict | None:
    soup = fetch(url)
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else None

    return {"url": url, "title": title, "price": price, "flavor_notes": flavor_notes,
            "weight_g": parse_weight_g(title)}


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    """理由はモジュールdocstring参照(150g/1kgの重複は最小重量のみ採用)。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_WEIGHT_PATTERN.sub("", item["title"])
        base = re.sub(r"[\s　]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for base, group in groups.items():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
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
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for url in product_urls:
        try:
            fields = fetch_fields(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if fields:
            all_items.append(fields)

    deduped = dedupe_by_base_name(all_items)

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeesupreme.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeesupreme.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
