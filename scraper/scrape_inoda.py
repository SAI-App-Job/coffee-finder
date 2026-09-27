# -*- coding: utf-8 -*-
"""
scrape_inoda.py

イノダコーヒ本店(store.inoda-coffee.co.jp、京都府京都市中京区堺町通三条下る
道祐町140、自家焙煎豆のオンライン販売)の商品情報を取得する。フューチャー
ショップ(JSON-LD Product、descriptionはHTML二重エスケープ)。

【店舗発見の経緯】
京都エリアの空白地調査で判明した「11店舗以上のチェーン」基準の境界線
ケース。1940年創業の老舗喫茶チェーンだが、現在の直営店舗数は8〜9店舗
(2023年時点9店舗、ピーク時13店舗)で「11店舗以上」の基準には該当しない
と判断し実装対象とした(ユーザーの指示によりチェーン店の定義に沿って
店舗数ベースで判定)。

【対象商品について】
実データ確認済み(/c/lineup/coffeebeans配下、2026-09時点): 全6商品
(アラビアの真珠・コロンビアのエメラルド・プレミアム・イノダジャーマン
ブレンド・エクストラ・イパネマの瑠璃、いずれも200g・ブレンド)を対象
とする。非対象商品なし。

【商品説明の構造について】
実データ確認済み: JSON-LDのdescriptionがHTMLエンティティで二重
エスケープされた構造化HTML(冒頭にテイスティング文の段落+table#specに
内容量/賞味期限/生豆生産国/サイズの仕様表)。html.unescape()でデコードし
BeautifulSoupで再パースする。table内の「生豆生産国」を配合国リストとして
farm_noteに、tableより前の段落をflavor_notesとして採用する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "イノダコーヒ本店",
    "url": "https://www.inoda-coffee.co.jp/",
    "platform": "フューチャーショップ",
    "address": "京都府京都市中京区堺町通三条下る道祐町140",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(フューチャーショップ標準構成を想定)",
}

BASE_URL = "https://store.inoda-coffee.co.jp"
PRODUCT_PATHS = [
    "/c/lineup/coffeebeans/102", "/c/lineup/coffeebeans/104", "/c/lineup/coffeebeans/106",
    "/c/lineup/coffeebeans/108", "/c/lineup/coffeebeans/118", "/c/lineup/coffeebeans/122",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)


def fetch_product(path: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}{path}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL)
    for b in blocks:
        try:
            data = json.loads(b)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


def parse_description(raw_desc: str) -> tuple[str | None, dict]:
    unescaped = html.unescape(raw_desc or "")
    soup = BeautifulSoup(unescaped, "html.parser")

    labels = {}
    table = soup.select_one("table#spec")
    if table:
        for tr in table.select("tr"):
            th, td = tr.select_one("th"), tr.select_one("td")
            if th and td:
                labels[th.get_text(strip=True)] = td.get_text(strip=True)
        table.decompose()

    text = soup.get_text("\n", strip=True)
    text = re.split(r"個別包装承ります|ギフトセット", text)[0].strip()
    return (text or None), labels


def build_record(path: str) -> dict | None:
    data = fetch_product(path)
    if not data:
        return None
    title = data["name"].replace("【豆】", "").strip()
    price = data.get("offers", {}).get("price")

    parsed = parse_product(title)
    url = f"{BASE_URL}{path}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    flavor_notes, labels = parse_description(data.get("description") or "")
    parsed = apply_category_hint_fallback(parsed, title)

    farm_note = f"生豆生産国：{labels['生豆生産国']}" if labels.get("生豆生産国") else None
    weight_m = WEIGHT_PATTERN.search(labels.get("内容量", "") or title)

    availability = (data.get("offers", {}).get("availability") or "").rstrip("/").split("/")[-1]
    structural_out_of_stock = availability not in ("InStock", "")
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for path in PRODUCT_PATHS:
        try:
            detail = build_record(path)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {path} ({e})")
            continue
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
    with open("data_inoda.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_inoda.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
