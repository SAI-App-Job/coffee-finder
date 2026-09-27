# -*- coding: utf-8 -*-
"""
scrape_wifeandhusband.py

WIFE&HUSBAND(wandh.buyshop.jp、京都府京都市北区小山下内河原町106-6、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(buyshop.jp、
thebase.inと同一エンジン)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。北山本店・京都駅店の他、ロースタリー「Roastery DAUGHTER
& Gallery SON」も同一オンラインストアを共有(3拠点)。

【対象商品について】
実データ確認済み(COFFEEカテゴリ全24件、2026-09時点): GIFT SET(4件、
複数銘柄セット)・DRIP BAG(2件、粉末パックでコーヒー豆単品と形態が異なる)
は非対象。残る18件は同一銘柄がBOX/PAPER PACK(包装違いのみで中身・価格が
ほぼ同じ)として重複展開されているため、BOX版を代表として採用し10銘柄
(ブレンド5:PICNIC・DAUGHTER・SON・MOTHER[デカフェ]・ストレート5:BRAZIL・
COLOMBIA・INDONESIA[マンデリン]・GUATEMALA・ETHIOPIA・FATHER)に統合する。

【FATHERについて】
実データ確認済み: 商品名は「浅煎り"FATHER"」で他のブレンド銘柄
(DAUGHTER/SON/MOTHER)と同じ命名規則だが、商品説明を確認したところ
実体はブラジル単一農園(Horizontina農園、ミナスジェライス州)のシングル
オリジンでありブレンドではない。カテゴリ判定は説明文の実態を優先しストレート
として収録する。

【商品説明について】
実データ確認済み: 大半の商品(BRAZIL/COLOMBIA/INDONESIA/GUATEMALA/
ETHIOPIA/DAUGHTER/SON)はog:descriptionが「WIFE&HUSBANDは京都にある
自家焙煎コーヒー店です。」という店舗紹介の定型文のみでテイスティング情報が
無い(flavor_notesはnullとする)。MOTHER・PICNIC・FATHERの3件のみ「◯」で
始まる詳細な商品説明(焙煎度・産地・ブランドストーリー)を持つため、
「(.....English follows)」以降の英語訳部分を除いた日本語部分を
flavor_notesとして採用する。
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
    "name": "WIFE&HUSBAND",
    "url": "https://www.wifeandhusband.jp/",
    "platform": "BASE(buyshop.jp)",
    "address": "京都府京都市北区小山下内河原町106-6",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://wandh.buyshop.jp"
CATEGORY_URL = f"{BASE_URL}/categories/2731730"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["GIFT SET", "DRIP BAG"]
STRIP_PACKAGE_PATTERN = re.compile(r"\s*(BOX|PAPER PACK)\s*$", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
GENERIC_DESC = "WIFE&HUSBANDは京都にある自家焙煎コーヒー店です。"


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch(CATEGORY_URL)
    urls = []
    seen = set()
    for a in soup.select('a[href*="/items/"]'):
        href = a.get("href", "")
        m = re.search(r"/items/(\d+)", href)
        if not m:
            continue
        url = f"{BASE_URL}/items/{m.group(1)}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_flavor_notes(desc: str) -> str | None:
    desc = desc.strip()
    if not desc or desc == GENERIC_DESC:
        return None
    # 「(.....English follows)」以降・「///...」区切り以降の英訳・注意書きを除去
    jp_part = re.split(r"\(\.{3,}English follows\)", desc)[-1] if "English follows" in desc else desc
    jp_part = re.split(r"/{5,}", jp_part)[0]
    jp_part = re.sub(r"^◯[^\n]*?(?=[ぁ-んァ-ヶ一-龥])", "", jp_part, count=1) if jp_part.startswith("◯") else jp_part
    return jp_part.strip() or None


def extract_fields(soup: BeautifulSoup, url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" / W&H COFFEE")[0].strip()
    if any(kw in title.upper() for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    desc = desc_el["content"] if desc_el and desc_el.get("content") else ""

    weight_m = WEIGHT_PATTERN.search(title)
    return {
        "url": url, "title": title, "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "raw_desc": desc,
    }


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_PACKAGE_PATTERN.sub("", item["title"])
        base = re.sub(r"[\s　]+", "", base).upper()
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        preferred = next((x for x in group if "box" in x["title"].lower()), group[0])
        result.append(preferred)
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

    flavor_notes = extract_flavor_notes(item["raw_desc"])

    # FATHERは商品名の命名規則上ブレンド判定されるが実体はブラジル単一農園の
    # ストレート(モジュールdocstring参照)。説明文からの再判定で上書きする。
    if "FATHER" in title.upper():
        parsed["category"] = "ストレート"
        parsed["origin_country"] = "ブラジル"
        parsed["origin_source"] = "product_description"
    else:
        origin_m = re.search(r"(?:原産国|ブレンド産地)：([^・\n]*)", item["raw_desc"])
        detected = (origin_m and detect_country_name(origin_m.group(1))) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if origin_m else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_m = re.search(r"精製処理：([^・\n]*)", item["raw_desc"])
    if processing_m:
        parsed["processing_method"] = normalize_processing_method(processing_m.group(1))

    roast_m = re.search(r"焙煎度：([^・\n]*)", item["raw_desc"])
    if roast_m:
        roast_parsed = parse_product(roast_m.group(1))
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
        "flavor_notes": flavor_notes,
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
    with open("data_wifeandhusband.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wifeandhusband.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
