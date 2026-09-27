# -*- coding: utf-8 -*-
"""
scrape_nishinaya.py

ニシナ屋珈琲(store.nishinaya.jp、京都府京都市上京区青龍町218[千本丸太町
焙煎所]、自家焙煎豆のオンライン販売)の商品情報を取得する。MakeShop
(新テンプレート、/view/item/形式)。

【店舗発見の経緯】
京都エリアの空白地調査で判明した「11店舗以上のチェーン」基準の境界線
ケース。広島発祥、広島5店舗・福岡1店舗・京都1店舗(千本丸太町焙煎所=
世界一カモ！焙煎所は同一店舗)の計7店舗のため「11店舗以上」の基準には
該当しないと判断し実装対象とした(ユーザーの指示によりチェーン店の定義に
沿って店舗数ベースで判定)。

【対象商品について】
実データ確認済み(/view/category/all_items、全37件、2026-09時点):
ドリップパック各種(4件)・水出しアイスコーヒー(1件)・珈琲セット/福袋類
(11件、複数銘柄セット)はNON_BEAN_KEYWORDSで除外。残り20件(ブレンド9・
ストレート11、うちワイルド コピ・ルアックは希少なジャコウネコ由来の
天然コーヒー)を収録。価格は容量選択式(100g〜500g)の先頭表示価格
(=最小容量100g相当)を採用する。

【商品説明の構造について】
実データ確認済み: 本文に「【コーヒー豆の特徴】(テイスティング文)」に
続いて「【コーヒー豆の詳細情報】商品名：/生産地：/品種：/精製方法：/
フレーバー：」という構造化ラベルが明記されている(この店舗特有の丁寧な
構成)。
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
    "name": "ニシナ屋珈琲",
    "url": "https://nishinaya.jp/",
    "platform": "MakeShop",
    "address": "京都府京都市上京区青龍町218",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(MakeShop標準構成を想定)",
}

BASE_URL = "https://store.nishinaya.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PIDS = [
    "000000000001", "000000000002", "000000000003", "000000000004", "000000000005",
    "000000000006", "000000000007", "000000000008", "000000000009", "000000000010",
    "000000000011", "000000000012", "000000000013", "000000000014", "000000000015",
    "000000000017", "000000000018", "000000000019", "000000000027", "000000000028",
]

LABEL_PATTERN = re.compile(r"^(商品名|生産地|品種|精製方法|フレーバー)\s*[：:]\s*(.+)$")


def fetch(pid: str) -> list[str]:
    resp = requests.get(f"{BASE_URL}/view/item/{pid}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [l.strip() for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]


def parse_content(lines: list[str]) -> tuple[str, int | None, str | None, dict]:
    title_idx = next((i for i, l in enumerate(lines) if l in ("焙煎豆",) or l == "ホーム"), None)
    # タイトルは「ホーム > カテゴリ > カテゴリ2 > 商品名」の直後
    home_idx = lines.index("ホーム") if "ホーム" in lines else None
    title = lines[home_idx + 3] if home_idx is not None and home_idx + 3 < len(lines) else lines[0]

    price = None
    price_idx = next((i for i, l in enumerate(lines) if l == "￥"), None)
    if price_idx is not None and price_idx + 1 < len(lines):
        m = re.search(r"[\d,]+", lines[price_idx + 1])
        if m:
            price = int(m.group().replace(",", ""))

    feat_idx = next((i for i, l in enumerate(lines) if l == "【コーヒー豆の特徴】"), None)
    detail_idx = next((i for i, l in enumerate(lines) if l == "【コーヒー豆の詳細情報】"), None)
    qty_idx = next((i for i, l in enumerate(lines) if l == "数量"), None)
    flavor_notes = None
    if feat_idx is not None:
        candidates = [i for i in (qty_idx, detail_idx) if i is not None and i > feat_idx]
        end = min(candidates) if candidates else feat_idx + 6
        flavor_notes = "\n".join(lines[feat_idx + 1:end]) or None

    labels = {}
    if detail_idx is not None:
        for line in lines[detail_idx + 1:detail_idx + 8]:
            m = LABEL_PATTERN.match(line)
            if m:
                labels[m.group(1)] = m.group(2).strip()

    return title, price, flavor_notes, labels


def build_record(pid: str) -> dict | None:
    lines = fetch(pid)
    title, price, flavor_notes, labels = parse_content(lines)
    title = re.sub(r"\s*焙煎\s*コーヒー\s*豆\s*$", "", title).strip()

    parsed = parse_product(title)
    url = f"{BASE_URL}/view/item/{pid}"
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

    origin_note = labels.get("生産地")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精製方法"])

    variety = labels.get("品種")
    if labels.get("フレーバー"):
        flavor_notes = (flavor_notes + "\n" if flavor_notes else "") + labels["フレーバー"]

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in TARGET_PIDS:
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
    with open("data_nishinaya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishinaya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
