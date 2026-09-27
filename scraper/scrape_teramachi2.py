# -*- coding: utf-8 -*-
"""
scrape_teramachi2.py

珈琲工房てらまち(coffee-teramachi.ocnk.net、京都府京都市中京区三条通大宮西入
上瓦町64-26、自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃのこ
ネット(Ocnk、product-list/N形式のURL)。

【店舗発見の経緯】
京都エリアの空白地調査(京都移住計画のコラム等)で発見。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「ブレンドコーヒー」(product-list/1、5件)・
「ストレートコーヒー」(product-list/2、14件)を対象とする。「季節限定品」
(product-list/27)は自家焙煎アーモンド・ピスタチオでコーヒー豆ではないため
対象外。

【価格について】
実データ確認済み: og:price等のmetaタグが無く、div.pricebに「販売価格：
780円～3,700円(税別)」という重量帯ごとの価格レンジのみが表示される
(100g/250g/500gの3重量、価格はバリアント選択時にJSで表示されるため
静的HTMLには個別価格が無い)。重量とほぼ比例した価格設定のため、レンジの
最小値(=100g相当)を代表価格として採用する。実データのレンジ区切り文字が
全角チルダ「～」(U+FF5E)であり、当初のPRICE_PATTERNが波ダッシュ「〜」
(U+301C)・半角チルダ「~」のみを対象としていたため全19商品でマッチ失敗し
price=Noneになっていた不具合を修正済み(全角チルダを追加)。

【商品説明について】
実データ確認済み: div.detail_desc_box内にテイスティング文+香り/苦味/酸味/
甘味/コクの★評価+生産国/生産地域/農園名/標高/品種/精製等のラベル(コロン
区切り、表記ゆれあり)が混在する。★評価行・配送案内定型文(「500gまでは
A4サイズのメール便」等)・引用元クレジット行は除外し、ラベル該当行を
構造化フィールドに反映、残りの自由記述文をflavor_notesとして採用する。

【エンコーディングについて】
実データ確認済み: ページ自体はcharset宣言があるが、requestsの既定
エンコーディング判定が外れるため、r.encoding="utf-8"を明示する必要が
あった。
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
    "name": "珈琲工房てらまち",
    "url": "https://coffee-teramachi.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "京都府京都市中京区三条通大宮西入上瓦町64-26",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のOcnk系店舗と同様の構成を想定)",
}

BASE_URL = "https://coffee-teramachi.ocnk.net"
CATEGORY_IDS = ["1", "2"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

LABEL_KEYS = ["生産国", "生産地域", "産地", "農園名", "農園", "標高", "産地標高", "品種",
              "栽培品種", "精製", "精製方法", "スクリーン", "収穫時期", "栽培面積"]
LABEL_PATTERN = re.compile(r"^(" + "|".join(LABEL_KEYS) + r")\s*[　:：]\s*(.+)$")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円\s*[〜～~]")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pids() -> list[str]:
    pids: set[str] = set()
    for cat in CATEGORY_IDS:
        soup = fetch(f"{BASE_URL}/product-list/{cat}")
        pids |= {m.group(1) for a in soup.select('a[href*="/product/"]')
                 if (m := re.search(r"/product/(\d+)", a.get("href", "")))}
    return sorted(pids)


def parse_desc(soup: BeautifulSoup) -> tuple[str | None, dict]:
    box = soup.select_one("div.detail_desc_box")
    if not box:
        return None, {}
    lines = [l.strip() for l in box.get_text("\n", strip=True).split("\n") if l.strip()]

    labels: dict[str, str] = {}
    flavor_lines = []
    for line in lines:
        if "★" in line or "☆" in line:
            continue
        if line.startswith("ж") or "メール便" in line or "着払い" in line:
            continue
        if line.startswith("文：") or line.startswith("文:"):
            continue
        m = LABEL_PATTERN.match(line)
        if m:
            labels.setdefault(m.group(1), m.group(2).strip())
            continue
        flavor_lines.append(line)

    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return flavor_notes, labels


def parse_price(soup: BeautifulSoup) -> int | None:
    el = soup.select_one("div.priceb")
    if not el:
        return None
    m = PRICE_PATTERN.search(el.get_text(" ", strip=True))
    return int(m.group(1).replace(",", "")) if m else None


def build_record(pid: str) -> dict | None:
    soup = fetch(f"{BASE_URL}/product/{pid}")
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip().lstrip(":")

    price = parse_price(soup)
    parsed = parse_product(title)
    url = f"{BASE_URL}/product/{pid}"

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

    flavor_notes, labels = parse_desc(soup)

    origin_note = labels.get("生産国") or labels.get("産地") or labels.get("生産地域")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if not detect_country_name(title) else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精製") or labels.get("精製方法")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種") or labels.get("栽培品種")
    farm_parts = [labels.get(k) for k in
                  ("農園名", "農園", "生産地域", "標高", "産地標高", "スクリーン") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

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
        "variety": variety,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids = fetch_pids()

    records = []
    flavored_records = []
    for pid in pids:
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
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
    with open("data_teramachi2.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_teramachi2.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
