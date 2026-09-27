# -*- coding: utf-8 -*-
"""
scrape_altroasters.py

alt. coffee roasters(altroasters.thebase.in、京都府京都市中京区神泉苑町28-4、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
高田馬場・渋谷エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、
京都エリアを調査した際にkoyo-coffee.com「京都のコーヒー豆専門店おすすめ50選」
記事経由で発見。

【対象商品について】
実データ確認済み(sitemap.xml全22件、2026-09時点): コーヒー豆単品8銘柄
(クリスマスブレンド・京都ブレンド・コスタリカ アナエロビックナチュラル・
カフェインレス(メキシコ)・タンザニア アルーシャ・コンゴ ケヘレ・
エチオピア グジG1・ホンジュラス ラパス)。ドリップバッグ・ナッツ類・
羊羹・コーヒー石鹸・竹炭・抹茶・トートバッグ・植物性ミルク(ボンソイ・
オーツミルク)・抽出器具(ドリッパー・ペーパーフィルター)・タンブラー・
ネックレスはNON_BEAN_KEYWORDSで除外。

【商品説明の構造について】
実データ確認済み: og:descriptionが「■産地：X■プロセス：Y(自由記述の
テイスティング文が区切りなくYに続く)■品名：Z■内容量：Ng■テイスト
ノート：W■ロースト：R※(注文方法の定型文・YouTube解説動画リンク)」という
構成。■プロセスの値と直後のテイスティング文が区切り無く連結しているため
構造化フィールド(processing_method)への分離はできない(産地・精製方法は
産地国検出とtitleパースに委ねる)。■を改行に置換し、内容量・品名の行を
除いたテキストをflavor_notesとして採用し、※以降の定型文・動画リンクは
除去する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "alt. coffee roasters",
    "url": "https://altcoffee-roasters.com/",
    "platform": "BASE",
    "address": "京都府京都市中京区神泉苑町28-4",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://altroasters.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバック", "ナッツ", "羊羹", "石鹸", "竹炭", "抹茶", "トートバック",
    "ボンソイ", "オーツミルク", "ドリッパー", "ペーパーフィルター", "タンブラー", "ネックレス",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
DROP_LABELS = {"内容量", "品名"}


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def clean_flavor_notes(desc: str) -> str | None:
    if not desc:
        return None
    # ※以降(注文方法の定型文)・《以降(動画リンク見出し)を除去
    desc = re.split(r"[※《]", desc)[0]
    lines = []
    for part in desc.split("■"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([^：]+)：(.*)$", part, re.DOTALL)
        if m and m.group(1) in DROP_LABELS:
            continue
        lines.append(part)
    text = "\n".join(lines).strip()
    return text or None


def parse_weight_g(desc: str, title: str) -> int | None:
    m = re.search(r"内容量：(\d+)\s*[gｇ]", desc or "")
    if m:
        return int(m.group(1))
    m = WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def extract_fields(soup: BeautifulSoup) -> dict | None:
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

    return {
        "title": title,
        "price": price,
        "weight_g": parse_weight_g(desc, title),
        "flavor_notes": clean_flavor_notes(desc),
    }


def build_record(item: dict, url: str) -> dict | None:
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
            "product_url": url,
        }

    parsed = apply_category_hint_fallback(parsed, title)
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
        "product_url": url,
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
        fields = extract_fields(soup)
        if not fields:
            continue
        detail = build_record(fields, url)
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
    with open("data_altroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_altroasters.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
