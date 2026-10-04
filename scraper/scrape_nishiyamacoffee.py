# -*- coding: utf-8 -*-
"""
scrape_nishiyamacoffee.py

西山珈琲(www.nishiyama-coffee.com、兵庫県姫路市坂元町126、注文後に焙煎して発送する
自家焙煎店)の商品情報を取得する。MakeShop。
(nishiyama-coffee.net はWixの別ドメインのため使用しない)

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(`/view/category/all_items`、214件・5ページ)の
うち、焙煎豆に当たるカテゴリ「ブレンド」(ct1)・「ストレートコーヒー」(ct203)・
「カフェインレス」(ct121)・「コンテスト・期間限定豆」(ct122)の和集合(49件)を
対象とする。ct203にはct121・ct122の商品も含まれる(重複はIDで除去)。
除外: 「【オフィス用】1kg」(業務用大容量。同銘柄の100g商品がある)、ドリップパック、
コーヒーバッグ、水出し、セット、生豆、ギフト、器具、紅茶等(上記カテゴリ外)。
各商品は「<銘柄>(浅煎り|中煎り|深煎り)100g」のように焙煎度・重量違いが別商品として
別ページ(`/view/item/N`)に分かれており、バリエーションは挽き方(豆のまま/中挽き等)のみ。
価格は100g(代表)の価格。

【価格・在庫について】
商品ページに「¥ 750 (税込)」表示、JSON-LDのoffers.priceも同額(税込)。在庫は
JSON-LDのoffers.availabilityで判定する。実データ確認では全214商品が`InStock`で、
販売中以外のものは確認できなかった(注文後焙煎のため在庫切れが生じにくい構造と
思われる)。売り切れ時は`OutOfStock`になる前提で判定ロジックを実装している。

【産地・焙煎度・精選について】
単一農園商品の詳細ページにある表(table.d_table)の「地域」「プロセス」
「焙煎度合い」から取得する。表がない商品は商品名から判定する。
プロセスの誤記「ナチュナル」は「ナチュラル」に補正する。焙煎度は商品名の
括弧内(浅煎り/中煎り/深煎り)をroast_hintとして保持する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "西山珈琲",
    "url": "https://www.nishiyama-coffee.com/",
    "platform": "MakeShop",
    "address": "兵庫県姫路市坂元町126",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.nishiyama-coffee.com"
BEAN_CATEGORIES = ["ct1", "ct203", "ct121", "ct122"]
CRAWL_DELAY_SECONDS = 0.5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["オフィス用", "ドリップ", "コーヒーバッグ", "水出し", "セット", "生豆", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gG]")
ROAST_HINT_PATTERN = re.compile(r"[(（]\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)\s*[)）]")
GENERIC_TAGLINES = {"ブレンド", "ストレートコーヒー　一覧", "ストレートコーヒー 一覧", "オフィスコーヒー", "カフェインレス", "コンテスト・期間限定豆"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_category_item_ids(cat: str) -> list[str]:
    ids: list[str] = []
    page = 1
    while True:
        url = f"{BASE_URL}/view/category/{cat}" + (f"?page={page}" if page > 1 else "")
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        for a in soup.select("a[href*='/view/item/']"):
            m = re.search(r"/view/item/(\d+)", a["href"])
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
        if not soup.select(f".pager a[href*='page={page + 1}']"):
            break
        page += 1
    return ids


def extract_product_ld(soup: BeautifulSoup) -> dict | None:
    for sc in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(sc.string or "")
        except json.JSONDecodeError:
            continue
        for node in data.get("@graph", [data]):
            if node.get("@type") == "Product":
                return node
    return None


def extract_spec_table(soup: BeautifulSoup) -> dict:
    spec = {}
    for tr in soup.select("table.d_table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            spec[th.get_text(strip=True)] = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
    return spec


def build_record(item_id: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    ld = extract_product_ld(soup)
    if not ld:
        return None
    raw = re.sub(r"\s+", " ", ld["name"].replace("　", " ")).strip()
    if any(kw in raw for kw in EXCLUDE_KEYWORDS):
        return None
    m = WEIGHT_PATTERN.search(raw)
    weight = int(m.group(1)) if m else None
    name = re.sub(r"\s*/\s*リピート率.*$", "", raw)
    name = re.sub(r"\s*\d+\s*[gG]\s*$", "", name).strip()

    offer = ld.get("offers") or {}
    price = int(float(offer["price"])) if offer.get("price") else None
    available = str(offer.get("availability", "")).endswith("InStock")

    spec = extract_spec_table(soup)
    category_label = ld.get("category") or ""
    is_blend = category_label == "ブレンド" or "ブレンド" in name

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"] and spec.get("地域"):
            c = detect_country_name(spec["地域"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    processing = parsed["processing_method"]
    if not processing and spec.get("プロセス"):
        raw_proc = spec["プロセス"].replace("ナチュナル", "ナチュラル")
        processing = normalize_processing_method(raw_proc)

    roast_hint = None
    mh = ROAST_HINT_PATTERN.search(name)
    if mh:
        roast_hint = mh.group(1)
    roast_level = parsed["roast_level"]
    spec_roast = spec.get("焙煎度合い")
    if spec_roast:
        roast_level = roast_level or parse_product(spec_roast)["roast_level"]
        if not roast_hint:
            mh2 = re.search(r"(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)", spec_roast)
            roast_hint = mh2.group(1) if mh2 else spec_roast

    notes_parts = []
    if category_label and category_label not in GENERIC_TAGLINES:
        notes_parts.append(category_label)
    rec_block = soup.find(string=re.compile(r"こんな(味わい|方)"))
    if rec_block:
        txt = re.sub(r"\s+", " ", rec_block.parent.get_text(" ", strip=True))
        notes_parts.append(txt)
    flavor_notes = " ".join(notes_parts)[:400] or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes,
        "farm_note": spec.get("地域"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/view/item/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    item_ids: list[str] = []
    for cat in BEAN_CATEGORIES:
        for i in fetch_category_item_ids(cat):
            if i not in item_ids:
                item_ids.append(i)
        time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    for item_id in item_ids:
        try:
            html = fetch_html(f"{BASE_URL}/view/item/{item_id}")
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_id} ({e})")
            continue
        rec = build_record(item_id, html)
        if rec:
            records.append(rec)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_nishiyamacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishiyamacoffee.json に出力しました")


if __name__ == "__main__":
    main()
