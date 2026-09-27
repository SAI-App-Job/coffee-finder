# -*- coding: utf-8 -*-
"""
scrape_yokoyama.py

よこやま珈琲(yokoyama1986.com、京都府宇治市小倉町西浦5-9、自家焙煎豆の
オンライン販売)の商品情報を取得する。独自EC(カート機能付きの一枚岩HTML、
プラットフォーム不明)。

【店舗発見の経緯】
京都エリアの空白地調査(ALCOグルメ等)で発見。1986年創業、SCAJ認定コーヒー
マイスターの店主による店。

【対象商品について】
実データ確認済み(2026-09時点): トップページの「シングルオリジン」
(11件)・「ブレンド」(8件)リンクを対象とする。「２０２６第２弾リキッド
アイスコーヒー１０００ml」(瓶詰め液体、1件)はNON_BEAN_KEYWORDSで除外。
残り18件(ストレート10・ブレンド8)を収録。

【商品説明・価格の構造について】
実データ確認済み: meta og:title/descriptionが存在しないため本文テキストを
直接解析する。ページ本文に「シングルオリジン」または「ブレンド」という
パンくずラベル行の直後に商品名が再掲され、そこから「拡大表示」という
文言が現れるまでがテイスティング文(+ストレート品のみ「生産者/地域/
標高/品種/精製」の生産履歴ラベル、各ラベルは表示上の字間調整で「地　域」
のように全角スペースが文字間に挿入されている)。価格は「(税込 X円)」形式
で本体価格の直後に記載されているため、税込価格を採用する。
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
    "name": "よこやま珈琲",
    "url": "https://www.yokoyama1986.com/",
    "platform": "独自EC",
    "address": "京都府宇治市小倉町西浦5-9",
    "prefecture": "京都府",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.yokoyama1986.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

HANDLES = [
    "bl_AaT", "bl_aisu", "bl_club", "bl_esupure", "bl_kouki5", "bl_mild", "bl_mokabure", "bl_yokoyama",
    "st_c-fatima-c", "st_c-fatima-fr", "st_dekaf-agusu-cc", "st_eirugagerenan-fc", "st_ferunando",
    "st_nrkfa-fr", "st_onanganjan", "st_peanma-fc", "st_png-gauri-h", "st_tz-tarime-c",
]

PRICE_PATTERN = re.compile(r"税込\s*([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"^(生\s*産\s*者|地\s*域|標\s*高|品\s*種|精\s*製)\s*[：:]\s*(.+)$")


def fetch(handle: str) -> list[str]:
    resp = requests.get(f"{BASE_URL}/SHOP/{handle}.html", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [l.strip() for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]


def parse_content(lines: list[str]) -> tuple[str, str | None, dict, int | None, int | None]:
    cat_indices = [i for i, l in enumerate(lines) if l in ("シングルオリジン", "ブレンド")]
    cat_idx = cat_indices[-1] if cat_indices else None
    title = lines[cat_idx + 1] if cat_idx is not None else lines[0]
    end_idx = next((i for i in range(cat_idx + 2, len(lines)) if lines[i] == "拡大表示"), len(lines)) \
        if cat_idx is not None else len(lines)
    block = lines[cat_idx + 2:end_idx] if cat_idx is not None else []

    flavor_lines = []
    labels = {}
    for line in block:
        m = LABEL_PATTERN.match(line)
        if m:
            key = re.sub(r"\s+", "", m.group(1))
            labels[key] = m.group(2).strip()
            continue
        if line.startswith("【焙煎士"):
            break
        flavor_lines.append(line)

    price = None
    for line in lines:
        m = PRICE_PATTERN.search(line)
        if m:
            price = int(m.group(1).replace(",", ""))
            break

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return title, ("\n".join(flavor_lines) or None), labels, price, weight_g


def build_record(handle: str) -> dict | None:
    lines = fetch(handle)
    title, flavor_notes, labels, price, weight_g = parse_content(lines)

    parsed = parse_product(title)
    url = f"{BASE_URL}/SHOP/{handle}.html"
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

    origin_note = labels.get("地域")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)
    if handle.startswith("bl_"):
        parsed["category"] = "ブレンド"

    if labels.get("精製"):
        parsed["processing_method"] = normalize_processing_method(labels["精製"])

    variety = labels.get("品種")
    farm_parts = [p for p in [labels.get("生産者"), labels.get("地域"), labels.get("標高")] if p]
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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for handle in HANDLES:
        try:
            detail = build_record(handle)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {handle} ({e})")
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
    with open("data_yokoyama.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yokoyama.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
