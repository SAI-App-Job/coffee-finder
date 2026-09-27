# -*- coding: utf-8 -*-
"""
scrape_shigacoffee.py

シガコーヒー(shigacoffee.thebase.in、京都府京都市下京区西七条御領町25-2、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。

【対象商品について】
実データ確認済み(sitemap.xml全27件、2026-09時点): コーヒー豆10銘柄
(ブレンドミドル・ブレンドフカイリ・ブラジル・グァテマラ・タンザニア・
メキシコ・パプアニューギニア・コスタリカ・インドネシア・ホンジュラス
デカフェ)×100g/200gの2重量展開。ドリップバックコーヒー・コーヒー保存缶
(シガコ缶)・マスキングテープ・水出しコーヒーパックはNON_BEAN_KEYWORDSで
除外。100g/200gの重複は最小重量側のみ採用する。

【商品説明の構造について】
実データ確認済み: og:descriptionが「(自由記述のテイスティング文)(ブレンド
のみ:銘柄名●豆1●豆2●豆3)◆品名：X◆内容量：Ng◆焙煎度：R※(粉希望時の
連絡方法等の定型文)」という構成。◆以降をラベル値として構造化フィールドに
反映し、◆より前の自由記述文をflavor_notesとして採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "シガコーヒー",
    "url": "https://www.shigacoffee.com/",
    "platform": "BASE",
    "address": "京都府京都市下京区西七条御領町25-2",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://shigacoffee.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバックコーヒー", "シガコ缶", "マステ", "水出しコーヒー"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
STRIP_WEIGHT_PATTERN = re.compile(r"[（(].*?[）)]|\s*\d+\s*[gｇ]\s*")
LABEL_PATTERN = re.compile(r"◆(品名|内容量|焙煎度)：([^◆※]*)")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def parse_weight_g(labels: dict, title: str) -> int | None:
    weight_label = labels.get("内容量", "")
    m = WEIGHT_PATTERN.search(weight_label)
    if m:
        return int(m.group(1))
    m = WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def extract_fields(soup: BeautifulSoup, url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    desc = desc_el["content"] if desc_el and desc_el.get("content") else ""

    labels = dict(LABEL_PATTERN.findall(desc))
    flavor_notes = re.split(r"◆|●", desc)[0].strip() or None

    return {
        "url": url, "title": title, "price": price,
        "weight_g": parse_weight_g(labels, title),
        "roast_label": labels.get("焙煎度"),
        "flavor_notes": flavor_notes,
    }


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

    parsed = apply_category_hint_fallback(parsed, title)
    if item.get("roast_label"):
        roast_parsed = parse_product(item["roast_label"])
        if roast_parsed.get("roast_level"):
            parsed["roast_level"] = roast_parsed["roast_level"]

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
    with open("data_shigacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shigacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
