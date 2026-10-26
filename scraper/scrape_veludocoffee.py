# -*- coding: utf-8 -*-
"""
scrape_veludocoffee.py

Veludo Coffee Roasters(ビロードコーヒーロースターズ、veludocoffee.theshop.jp、静岡県浜松市中央区
松小池町740-1、2026年8月開業の浅煎り専門コーヒーショップ)の商品情報を取得する。
BASE(theshop.jpドメイン)。

【店舗発見の経緯】
静岡県の再調査の新規発掘で発見(Instagramハンドルからのストア推測で実在を確認)。

【対象商品について】
実データ確認済み(2026-10時点): BASE全8商品(/items/all)すべてが自家焙煎のコーヒー豆
(シングルオリジン。150gが7、100gが1)。ドリップバッグ・セット・器具の商品は一覧にない。
商品名と重量は商品ページのタイトル(「Vietnam Lam Dong ... 150g」)から取得する。
店のABOUTに「浅煎り専門」「一つひとつの豆に合わせて焙煎しています」とあるが、商品ごとの焙煎度表記は
ないため roast_level はNone(roast_hintに店の方針を保持)。精製はOG説明の「Process:」項目から取得する
(Colombia Campo Hermosoの「Green Apple Mosto Co-Fermentation」はカルチャード・イースト＋果汁を使う
発酵プロセスの記載で、後添加のフレーバー付けではないため収録)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
実データ確認済み(2026-10-26): 他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用し、
リクエスト間隔は5秒。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "Veludo Coffee Roasters",
    "url": "https://veludocoffee.theshop.jp/",
    "platform": "BASE",
    "address": "静岡県浜松市中央区松小池町740-1",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://veludocoffee.theshop.jp/items/all)の全8商品と各商品ページ・/aboutを2026-10-26に確認。住所は静岡新聞アットエスのグルメ記事 https://www.at-s.com/gourmet/article/2037113 (2026年8月オープン)。BASEの特商法ページはBASE社住所のため住所根拠にならない。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://veludocoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.0

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ITEM_LINK_PATTERN = re.compile(r'href="https://veludocoffee\.theshop\.jp/items/(\d+)"')
SIZE_PATTERN = re.compile(r"\s*(\d+)\s*g\s*$")
PROCESS_PATTERN = re.compile(r"Process\s*[:：]\s*(.+?)\s*Image\s*[:：]")


def get(url: str) -> requests.Response:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp


def list_item_ids() -> list[str]:
    resp = get(f"{BASE_URL}/items/all")
    ids: list[str] = []
    for m in ITEM_LINK_PATTERN.finditer(resp.text):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def build_record(item_id: str) -> dict | None:
    resp = get(f"{BASE_URL}/items/{item_id}")
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: item_id={item_id} ({resp.status_code})")
        return None
    text = resp.text
    title_m = TITLE_PATTERN.search(text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", html.unescape(title_m.group(1)).split(" | ")[0]).strip()
    size_m = SIZE_PATTERN.search(title)
    weight = int(size_m.group(1)) if size_m else None
    name = SIZE_PATTERN.sub("", title).strip()

    desc_m = DESC_PATTERN.search(text)
    full_desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip() if desc_m else ""
    if full_desc == "少々お待ちください":  # 説明が未入力のときのBASEの仮文言
        full_desc = ""
    desc = full_desc[:400] or None
    roast_m = re.search(r"当店唯一の(中煎り)", full_desc)
    proc_m = PROCESS_PATTERN.search(full_desc)
    process_text = proc_m.group(1) if proc_m else ""
    price_m = PRICE_PATTERN.search(text)
    pur_m = PURCHASABILITY_PATTERN.search(text)
    sold_out = bool(pur_m) and pur_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if not parsed["origin_country"]:
        detected = detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": "ストレート",
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": detect_processing_method(process_text) or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_m.group(1) if roast_m else None,
        "roast_hint": "浅煎り専門店(ABOUTに記載。商品ごとの焙煎度表記なし)",
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in list_item_ids():
        try:
            rec = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: item_id={item_id} ({e})")
            continue
        if rec is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_veludocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_veludocoffee.json に出力しました")


if __name__ == "__main__":
    main()
