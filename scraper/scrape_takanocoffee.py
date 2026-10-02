# -*- coding: utf-8 -*-
"""
scrape_takanocoffee.py

タカノ珈琲(takano-coffee.co.jp、埼玉県川口市中青木2-3-40、1950年創業、ドイツ・
プロバット社の焙煎機で自社焙煎する工場直販の挽き売り店。店舗は川口の1店のみ)の
商品情報を取得する。EC-CUBE系のウェブショップ。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧のうち焙煎豆の5カテゴリ
(中煎り29・中深煎り30・深煎り31・有機100%使用32・限定品プレミアム39)を対象とする。
送料無料セット・ドリップバッグ・リキッド・インスタント・水出しバッグ・ギフトは除外。
内容量は商品ページの「内容量 200g」から取得し、焙煎度合は「焙煎度合」欄から取得する。
商品名の先頭にある「焙煎士お薦め/人気ナンバー」等の販促ラベルは名称に含めない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "タカノ珈琲",
    "url": "https://www.takano-coffee.co.jp/",
    "platform": "EC-CUBE",
    "address": "埼玉県川口市中青木2-3-40",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.takano-coffee.co.jp/shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = [29, 30, 31, 32, 39]
ROAST_PATTERN = re.compile(r"(浅煎り|中浅煎り|中深煎り|中煎り|深煎り|イタリアンロースト|フレンチロースト)")


def lines_of(url: str) -> list[str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]


def list_item_ids() -> list[str]:
    ids: list[str] = []
    for cid in CATEGORY_IDS:
        resp = requests.get(f"{BASE_URL}/products/list?category_id={cid}", headers=REQUEST_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        for item_id in re.findall(r"/products/detail/(\d+)", resp.text):
            if item_id not in ids:
                ids.append(item_id)
    return ids


def build_record(item_id: str) -> dict | None:
    lines = lines_of(f"{BASE_URL}/products/detail/{item_id}")

    # 先頭ブロック: 「内容量 200g」の直前が商品名(販促ラベルがある場合は直前の行が商品名)
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.startswith("内容量"))
    except StopIteration:
        return None
    name = lines[idx - 1]
    weight_m = re.search(r"(\d+)\s*[gｇ]", lines[idx])
    weight_g = int(weight_m.group(1)) if weight_m else None

    def after(label: str) -> str | None:
        for i, ln in enumerate(lines):
            if ln == label and i + 1 < len(lines):
                return lines[i + 1]
        return None

    price_idx = next((i for i, ln in enumerate(lines) if ln.startswith("販売価格(税込)")), None)
    price = None
    if price_idx is not None:
        m = re.search(r"([\d,]+)", lines[price_idx + 1])
        price = int(m.group(1).replace(",", "")) if m else None

    roast_text = after("焙煎度合") or ""
    roast_m = ROAST_PATTERN.search(roast_text)
    country = after("生産国") or after("生豆生産国")
    desc = lines[idx + 2] if idx + 2 < len(lines) else None
    out_of_stock = any("在庫なし" in ln or "在庫無し" in ln or "SOLD OUT" in ln.upper() for ln in lines[max(0, idx - 4):idx + 1])

    parsed = parse_product(name)
    # 生豆生産国が複数(読点区切り)の商品は配合品(アイスコーヒー等)なのでブレンド扱い
    if "ブレンド" in name or (country and "、" in country):
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and country and "ブレンド" not in name:
            c = detect_country_name(country)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_m.group(1) if roast_m else parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": f"{BASE_URL}/products/detail/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in list_item_ids():
        try:
            record = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_takanocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_takanocoffee.json に出力しました")


if __name__ == "__main__":
    main()
