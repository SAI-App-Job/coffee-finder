# -*- coding: utf-8 -*-
"""
scrape_sepiacf.py

珈琲工房セピア(sepia.shop-pro.jp、公式 https://www.sepia-cf.com/、香川県坂出市京町3丁目1-3)の
商品情報を取得する。カラーミーショップ(EUC-JP)。

【対象商品について】
実データ確認済み(2026-10-15): カテゴリ「ブレンドコーヒー」(cbid=1774072)と
「ストレートコーヒー」(cbid=1788657)の商品がコーヒー豆。ドリップバッグ・リキッド
アイスコーヒー・コーヒーバッグ・ゼリー・ギフトは別カテゴリのため対象外。
バリエーションは「豆/粉 × 200g/500g」で、豆のまま×最小重量(200g)を代表とする。
商品説明の先頭に焙煎度(ハイ/シティ/フレンチ/イタリアンロースト)が書かれている。
在庫: inventory_control=none のため構造化された在庫フラグは無く、カート部の売り切れ表記で判定。
特定商取引法ページ(?mode=sk)の販売業者は「珈琲工房　セピア」、住所は香川県坂出市京町3丁目1-3。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    detect_stock_status,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "珈琲工房セピア",
    "url": "https://sepia.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "香川県坂出市京町3丁目1-3",
    "prefecture": "香川県",
    "robots_txt_status": "未確認(カラーミーショップ標準構成)",
}

BASE_URL = "https://sepia.shop-pro.jp/"
CATEGORIES = [("1774072", "ブレンド"), ("1788657", "ストレート")]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"^\s*(フルシティ|シティ|ハイ|ミディアム|フレンチ|イタリアン|ライト|シナモン)ロースト")
PID_PATTERN = re.compile(r"\?pid=(\d+)")
SOLD_OUT_PATTERN = re.compile(r"SOLD\s*OUT|売り切れ|品切れ|入荷待ち", re.I)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("euc-jp", errors="replace")


def collect_pids() -> list[tuple[str, str]]:
    found = []
    seen = set()
    for cbid, label in CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0" + (f"&page={page}" if page > 1 else "")
            html = fetch(url)
            time.sleep(CRAWL_DELAY_SECONDS)
            pids = []
            for pid in PID_PATTERN.findall(html.split('<div id="main">')[-1]):
                if pid not in pids:
                    pids.append(pid)
            new = [p for p in pids if p not in seen]
            if not new:
                break
            for p in new:
                seen.add(p)
                found.append((p, label))
            if f"page={page + 1}" not in html:
                break
            page += 1
    return found


def build_record(pid: str, label: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html = fetch(url)
    m = COLORME_JSON_PATTERN.search(html)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    soup = BeautifulSoup(html, "html.parser")
    name_el = soup.select_one("h2.product_name")
    title = (name_el.get_text(strip=True) if name_el else product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)

    desc_el = soup.select_one("div.product_description")
    desc_full = desc_el.get_text("\n", strip=True) if desc_el else ""
    desc_main = desc_full.split("【ローストについて】")[0].strip()
    roast_m = ROAST_PATTERN.search(desc_main)
    roast_level = None
    if roast_m:
        roast_level = parse_product(roast_m.group(0))["roast_level"]
        desc_main = desc_main[roast_m.end():].strip()
    desc = re.sub(r"\s+", " ", desc_main)[:400] or None

    candidates = []
    for v in product.get("variants", []):
        wm = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        if wm and (v.get("option1_value") or "") == "豆":
            candidates.append((int(wm.group(1)), v))
    if not candidates:
        return None
    weight, variant = min(candidates, key=lambda x: x[0])

    cart_area = soup.select_one("div.add_cart")
    sold_out_text = bool(cart_area and SOLD_OUT_PATTERN.search(cart_area.get_text(" ")))
    stock_status = detect_stock_status(title, sold_out_text)

    parsed = parse_product(title)
    if label == "ブレンド" or "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        # 「東チモール」(辞書は「東ティモール」表記)
        if not parsed["origin_country"] and "東チモール" in title:
            parsed["origin_country"] = "東ティモール"
            parsed["origin_source"] = "raw_name"
        # 説明文に精製方法の記載がある場合(例: エチオピア「ナチュラル精製豆」)
        if not parsed["processing_method"]:
            pm = re.search(r"(ナチュラル|ウォッシュド|ハニー)(?:精製|プロセス|製法)", desc_main)
            if pm:
                parsed["processing_method"] = detect_processing_method(pm.group(1))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax"),
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, label in collect_pids():
        try:
            rec = build_record(pid, label)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: pid={pid} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sepiacf.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sepiacf.json に出力しました")


if __name__ == "__main__":
    main()
