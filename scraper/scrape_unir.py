# -*- coding: utf-8 -*-
"""
scrape_unir.py

Unir(unir-coffee.shop、京都府長岡京市、自家焙煎豆のオンライン販売)の
商品情報を取得する。カラーミーショップ(EUC-JPエンコーディング)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。2006年創業、長岡京本店の他に京都店・The Unir Coffee
Senses(東山区)等複数拠点を展開するが全国100店舗以上への卸売りが中心で
直営店舗数は11未満のため「11店舗以上の大手チェーン」基準には該当しない。

【エンコーディングについて】
実データ確認済み: サイト全体がEUC-JPでエンコードされている(UTF-8では
文字化けする)。requests.Response.encodingを明示的に"euc-jp"に設定する
必要がある。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「シングルオリジン」(cbid=1176135)・
「ブレンド」(cbid=1176136)・「その他コーヒー豆」(cbid=1176140、Cool Sweet
スーパーエクセレントシリーズのみ対象)を対象とする。定期便(複数カテゴリに
重複掲載、月替わりでSKUが固定されない)・ドリップバッグ・水出しアイス
コーヒーパック・アイスコーヒーリキッドはNON_BEAN_KEYWORDSで除外。

【商品説明の構造について】
実データ確認済み: og:descriptionは店舗紹介の定型文のみで情報が無い。
section.c-product-detail内に「TASTING NOTES: (英語)(日本語訳)(自由記述の
テイスティング文)農園: X生産者: Y地域: Z標高: W品種: V プロセス: U」という
構成で、末尾にギフトラッピング等の定型文・ニュース記事へのリンクが続く。
ラベル値を構造化フィールドに反映し、ラベルより前のテイスティング文を
flavor_notesとして採用、「ギフトラッピング」以降は除去する。
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
    "name": "Unir",
    "url": "https://unir-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "京都府長岡京市",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(カラーミーショップ標準構成を想定)",
}

BASE_URL = "https://unir-coffee.shop"
CATEGORY_IDS = ["1176135", "1176136", "1176140"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["定期便", "ドリップバッグ", "水出しアイスコーヒー", "アイスコーヒーリキッド"]
LABEL_PATTERN = re.compile(r"(農園|生産者|地域|標高|品種|プロセス)[：:]\s*([^\n]*)")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pids() -> list[str]:
    pids: set[str] = set()
    for cbid in CATEGORY_IDS:
        resp = requests.get(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0", headers=REQUEST_HEADERS, timeout=20)
        resp.encoding = "euc-jp"
        pids |= set(re.findall(r"pid=(\d+)", resp.text))
    return sorted(pids)


def extract_flavor_notes_and_labels(soup: BeautifulSoup) -> tuple[str | None, dict]:
    section = soup.select_one("section.c-product-detail")
    if not section:
        return None, {}
    text = section.get_text("\n", strip=True)
    text = text.split("ギフトラッピング")[0]

    label_positions = [(m.start(), m.end(), m.group(1)) for m in LABEL_PATTERN.finditer(text)]
    labels = {}
    for i, (start, end, key) in enumerate(label_positions):
        value_end = label_positions[i + 1][0] if i + 1 < len(label_positions) else len(text)
        labels[key] = text[end:value_end].strip().strip("\n")

    flavor_text = text[:label_positions[0][0]] if label_positions else text
    flavor_text = re.sub(r"^TASTING NOTES\s*[:：]?\s*", "", flavor_text.strip())
    return (flavor_text.strip() or None), labels


def build_record(pid: str) -> dict | None:
    soup = fetch(f"{BASE_URL}/?pid={pid}")
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" - SPECIALTY COFFEE")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    section_text = (soup.select_one("section.c-product-detail") or soup).get_text(" ", strip=True)
    if "リキッド" in section_text or "瓶詰め" in section_text:
        # 「Cool Sweet」のように商品名だけではボトル入り液体コーヒーと判別できない
        # ケースがあるため本文からも除外判定する(実データ確認済み)
        return None

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": f"{BASE_URL}/?pid={pid}",
        }

    flavor_notes, labels = extract_flavor_notes_and_labels(soup)

    origin_note = labels.get("地域")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("プロセス")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種")
    farm_parts = [p for p in [labels.get("農園"), labels.get("生産者"), labels.get("標高")] if p]
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
        "product_url": f"{BASE_URL}/?pid={pid}",
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
    with open("data_unir.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_unir.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
