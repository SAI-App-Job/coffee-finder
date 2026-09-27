# -*- coding: utf-8 -*-
"""
scrape_3scoffee.py

3s...COFFEE ROASTER(3scr.base.shop、京都府京都市伏見区横大路下三栖梶原町、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。

【対象商品について】
実データ確認済み(sitemap.xml全29件、2026-09時点): コーヒー豆17銘柄
(ブレンド2・ストレート14・デカフェ1)。ナッツ類(アーモンド・ヘーゼル
ナッツ・ピスタチオ・カシューナッツ・ピーナッツ・ミックスナッツ)・
COLD BREW Coffee Pack(2種、粉末パックでありコーヒー豆単品とは形態が
異なる)・TEA BAG coffeeはNON_BEAN_KEYWORDSで除外。「販売終了」表記の
商品([ボリビア]マイクロロット等)もコーヒー豆自体は実在した商品のため
収録し、stock_statusで終売扱いとする。

【重量について】
実データ確認済み: 商品名に重量表記が無く、商品説明に「100g単位でご注文
いただけます(200g〜は数量を増やして)」とあるため、基準単位の100gを
weight_gとして採用する(価格は100gあたりの単価)。

【商品説明の構造について】
実データ確認済み: og:descriptionが「【銘柄名】☆Specialty Coffee生産国：
X生産地域：Y農園名：Z農園樹種：W標高：V精製：U(自由記述のテイスティング文)
当店では...(注文方法・保存期間等の定型文)」という構成。「当店では」以降
(全商品共通の定型文)を除去し、精製：の値より後・「当店では」より前の
自由記述文をflavor_notesとして採用する。
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
    "name": "3s...COFFEE ROASTER",
    "url": "https://3scr.base.shop/about",
    "platform": "BASE",
    "address": "京都府京都市伏見区横大路下三栖梶原町35-1-36",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://3scr.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "アーモンド", "ヘーゼルナッツ", "ピスタチオ", "カシューナッツ", "ピーナッツ",
    "ミックスナッツ", "COLD BREW", "TEA BAG",
]


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def parse_description(desc: str) -> tuple[dict, str | None]:
    labels = {}
    # ラベルを順に切り出す(値は次のラベルまたは末尾まで)
    label_positions = [(m.start(), m.end(), m.group(1)) for m in re.finditer(
        r"(生産国|生産地域|農園名|農園樹種|標高|精製)：", desc)]
    for i, (start, end, key) in enumerate(label_positions):
        value_end = label_positions[i + 1][0] if i + 1 < len(label_positions) else len(desc)
        labels[key] = desc[end:value_end].strip()

    tail_start = label_positions[-1][0] if label_positions else 0
    # 精製の値の末尾(次のラベルが無い場合の残り全文)から、テイスティング文+定型文が続く
    remainder = desc[label_positions[-1][1]:] if label_positions else desc
    # 「当店では」以降の定型文を除去
    remainder = re.split(r"当店では", remainder)[0]
    # 精製の値自体(短い精製方法名)とテイスティング文が区切りなく連結しているため、
    # 精製ラベルの値は正規化関数に丸ごと渡し、flavor_notesにはremainder全体を採用する
    if "精製" in labels:
        labels["精製_full"] = labels["精製"]
    flavor_notes = remainder.strip() or None
    return labels, flavor_notes


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

    labels, flavor_notes = parse_description(desc)
    return {"url": url, "title": title, "price": price, "labels": labels, "flavor_notes": flavor_notes}


def build_record(item: dict) -> dict | None:
    title = re.sub(r"^[【\[][^】\]]*[】\]]\s*", "", item["title"]).strip()
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

    labels = item["labels"]
    origin_note = labels.get("生産国") or labels.get("生産地域")
    if origin_note:
        detected = detect_country_name(origin_note) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精製_full") or labels.get("精製")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    farm_parts = [p for p in [labels.get("農園名"), labels.get("農園樹種"), labels.get("標高")] if p]
    farm_note = "、".join(farm_parts) if farm_parts else None

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
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for url in item_urls:
        try:
            soup = fetch(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        fields = extract_fields(soup, url)
        if not fields:
            continue
        detail = build_record(fields)
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
    with open("data_3scoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_3scoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
