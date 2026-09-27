# -*- coding: utf-8 -*-
"""
scrape_amatista.py

AMATISTA Coffee(amatistacoffee.shop-pro.jp、京都府宇治市宇治妙楽171-13、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp旧ドメイン、EUC-JPエンコーディング)。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp等)で発見。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「スタンダード」(cbid=2451274、3件)・
「ブレンド」(cbid=2491549、4件)・「スペシャリティー」(cbid=2491553、
12件)・「年間数量限定品」(cbid=2491554、4件)を対象とする。うち
「IRISH CREAM COLOMBIAN COFFEE」「ピーチミルク.インフューズド
ファーメンテーションプロセス」の2件は商品説明を確認したところ原産国・
標高等の産地情報が一切無くフレーバー付け(アイリッシュクリーム/ピーチ
ミルクの香り付け)のみを謳う商品のため、NON_BEAN_KEYWORDSで除外する
(「コロンビア.ラム」は原産国・産地・品種・標高・SCAスコアが明記された
実在の産地コーヒーのため対象に含める)。

【商品説明について】
実データ確認済み: og:descriptionにテイスティング文が入っているが、
「原産国：X 産地：Y 品種：Z 標高：W SCAスコア：V」という構造化ラベルを
持つ商品と、純粋な自由記述の商品が混在する。ラベルが検出できた場合は
構造化フィールドに反映し、ラベルより前の文章をflavor_notesとして採用。
ラベルが無い場合は説明文全体をそのままflavor_notesとして採用する。

【エンコーディングについて】
実データ確認済み: EUC-JPページのためrequests取得時にr.encoding="euc-jp"
の明示が必要。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "AMATISTA Coffee",
    "url": "https://amatistacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "京都府宇治市宇治妙楽171-13",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のカラーミーショップ系店舗と同様の構成を想定)",
}

BASE_URL = "https://amatistacoffee.shop-pro.jp"
CATEGORY_IDS = ["2451274", "2491549", "2491553", "2491554"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["IRISH CREAM", "ピーチミルク"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"(原産国|産地|品種|標高|精製|精製方法|SCAスコア)\s*[：:]\s*([^原産国産地品種標高精製SCA]*?)(?=原産国|産地|品種|標高|精製|SCAスコア|$)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def fetch_pids() -> list[str]:
    pids: set[str] = set()
    for cbid in CATEGORY_IDS:
        text = fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0")
        pids |= set(re.findall(r"pid=(\d+)", text))
    return sorted(pids)


def parse_desc(desc: str) -> tuple[str | None, dict]:
    label_positions = [(m.start(), m.group(1), m.group(2).strip()) for m in LABEL_PATTERN.finditer(desc)]
    labels = {}
    for _, key, value in label_positions:
        labels.setdefault(key, value)
    flavor_text = desc[:label_positions[0][0]] if label_positions else desc
    return flavor_text.strip() or None, labels


def build_record(pid: str) -> dict | None:
    text = fetch(f"{BASE_URL}/?pid={pid}")
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', text)
    if not title_m:
        return None
    title = title_m.group(1).split(" - AMATISTA")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', text)
    price = int(float(price_m.group(1))) if price_m else None
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', text)
    desc = desc_m.group(1) if desc_m else ""

    parsed = parse_product(title)
    url = f"{BASE_URL}/?pid={pid}"
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

    flavor_notes, labels = parse_desc(desc)

    origin_note = labels.get("原産国") or labels.get("産地")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精製") or labels.get("精製方法")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種")
    farm_parts = [p for p in [labels.get("産地"), labels.get("標高"), labels.get("SCAスコア")] if p]
    farm_note = "、".join(farm_parts) if farm_parts else None

    weight_m = WEIGHT_PATTERN.search(title)
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
        "weight_g": int(weight_m.group(1)) if weight_m else None,
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
    with open("data_amatista.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amatista.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
