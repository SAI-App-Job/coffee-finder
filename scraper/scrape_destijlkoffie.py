# -*- coding: utf-8 -*-
"""
scrape_destijlkoffie.py

デ・スティル コーフィー(destijlkoffie.com、宮城県仙台市青葉区一番町2丁目
5-5、自家焙煎豆のオンライン販売)の商品情報を取得する。独自EC(らく～る
カートASP利用)。

【店舗発見の経緯】
全国再調査(宮城県)で発見(kitsune-coffee.com「仙台のおすすめコーヒー豆
専門店18選」)。1982年創業、一番町店・大町店の2拠点+本社焙煎室を持つ
老舗ロースター。

【対象商品について】
実データ確認済み(2026-09時点): 「単一産地豆 SINGLE ORIGIN KOFFIE」
(categoryId=54344、全11件)・「ブレンド豆 BLEND KOFFIE」
(categoryId=54340、全13件)の計24件(ストレート11・ブレンド13)を対象と
する。水出しコーヒー・ペーパーフィルター等のグッズ・ギフトパッケージの
各カテゴリは対象外。全商品が税込価格／200gパックで統一されている。

【商品説明の構造について】
実データ確認済み: `div.item-detail-txt1`内にHTML装飾(font/span)混じりの
自由記述と、ストレート商品のみ「産地：/農園 :/標高：/品種：/サイズ：/
精製：」の構造化ラベル行が含まれる。冒頭に商品名を各種表記(カタカナ/
英語表記)で繰り返す行があり、平仮名を含まないため「ひらがなを含まない
行は名称の繰り返しとみなして除外し、ひらがなを含む行または構造化ラベル
行のみを採用する」というヒューリスティックで、名称重複行・評価記号行
(例:「中性：◎」)を排除しつつ本文を抽出する。本文末尾に長い「---」の
区切り線があり、以降はその産地全般に関する一般論(商品固有情報ではない)
のため区切り線以降は除去する。

【ブレンド商品のorigin_country誤検出について】
実データ確認済み: ブレンド商品の説明文には「インドネシアの二つの島の
コーヒー」「エチオピアのおもてなし」のように特定国名が頻出するため、
detect_country_name()がブレンド商品にも単一の産地国を誤って設定して
しまう。ブレンドは複数産地の配合であり単一国を代表させるのは不正確
なため、is_blend時は産地国検出処理自体をスキップする。
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
    "name": "デ・スティル コーフィー",
    "url": "https://destijlkoffie.com/",
    "platform": "独自EC(らく～る)",
    "address": "宮城県仙台市青葉区一番町2丁目5-5",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(独自EC構成)",
}

BASE_URL = "https://destijlkoffie.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

STRAIGHT_IDS = [
    "859098", "859905", "859920", "859913", "859918", "859921",
    "859100", "859101", "859102", "865693", "861964",
]
BLEND_IDS = [
    "860648", "860645", "860649", "860650", "860651", "860653",
    "860652", "860655", "860654", "860656", "1930151", "860657", "897374",
]

HIRAGANA_PATTERN = re.compile(r"[ぁ-ゖ]")
LABEL_PATTERN = re.compile(r"^(産地|農園|標高|品種|サイズ|精選|精製)\s*[:：]\s*(.+)$")
SEPARATOR_PATTERN = re.compile(r"^-{5,}$")


def parse_desc(desc_el) -> tuple[str | None, dict]:
    lines = [l.strip() for l in desc_el.get_text("\n", strip=True).split("\n") if l.strip()]
    labels: dict[str, str] = {}
    flavor_lines = []
    for line in lines:
        if SEPARATOR_PATTERN.match(line):
            break
        m = LABEL_PATTERN.match(line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
            continue
        if HIRAGANA_PATTERN.search(line):
            flavor_lines.append(line)
    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return flavor_notes, labels


def build_record(pid: str, is_blend: bool) -> dict | None:
    resp = requests.get(f"{BASE_URL}/item-detail/{pid}", headers=REQUEST_HEADERS, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    title_el = soup.select_one("title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True).split(" | ")[0].strip()

    price_el = soup.select_one(".price.raku-item-vari-price-num")
    price = int(re.sub(r"[^\d]", "", price_el.get_text())) if price_el else None
    desc_el = soup.select_one(".item-detail-txt1")
    flavor_notes, labels = parse_desc(desc_el) if desc_el else (None, {})

    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        # parse_product()が地域名逆引き(例:「トラジャ」→インドネシア、
        # 「ハラール」→エチオピア)で単一産地国を設定してしまう場合がある。
        # ブレンドは複数産地の配合のため単一国指定は不正確、クリアする。
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    url = f"{BASE_URL}/item-detail/{pid}"
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

    origin_note = labels.get("産地")
    if not is_blend:
        detected = (
            (origin_note and detect_country_name(origin_note))
            or detect_country_name(title)
            or (flavor_notes and detect_country_name(flavor_notes))
        )
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if origin_note else "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    proc_note = labels.get("精選") or labels.get("精製")
    if proc_note:
        parsed["processing_method"] = normalize_processing_method(proc_note)

    variety = labels.get("品種")
    farm_parts = [f"{k}: {labels[k]}" for k in ("産地", "農園", "標高", "品種", "サイズ", "精選", "精製") if labels.get(k)]
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
        "weight_g": 200,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in STRAIGHT_IDS:
        try:
            detail = build_record(pid, is_blend=False)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    for pid in BLEND_IDS:
        try:
            detail = build_record(pid, is_blend=True)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_destijlkoffie.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_destijlkoffie.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
