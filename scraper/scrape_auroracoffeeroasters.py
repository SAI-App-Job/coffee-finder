# -*- coding: utf-8 -*-
"""
scrape_auroracoffeeroasters.py

Aurora Coffee Roasters(auroracoffeeroasters.jp、岩手県岩手郡雫石町上野二ツ森2-2、
スペシャルティコーヒー専門の自家焙煎店)の商品情報を取得する。
独自EC基盤(xaas3.jp)。又吉コーヒー園・下町コーヒー等と同じカートシステム。
(同名に近い scrape_auroracoffee.py は山形県のオーロラコーヒー(カラーミー)で別店舗)

robots.txt確認済み(2026-10-13、https://www.auroracoffeeroasters.jp/robots.txt):
/default/error/・/preview/のみDisallow。それ以外は制限なし。

【取得対象カテゴリ】
実データ確認済み: トップのナビにカテゴリ2(ブレンド)・5(トップ・オブ・トップ)・6(トップ・スペシャルティ)・
7(スペシャルティ)・8(ドリップバッグ)・9(EQUIPMENT)・11/14/15(プロセス別: ナチュラル/ウォッシュド/発酵)がある。
カテゴリ8(ドリップバッグ)と9(器具)は対象外。残りの7カテゴリは商品が重複して載っているため
(例: 同じロットがカテゴリ6と14に載る)、商品ID(/item/NN/)で重複を除く。1ページ24件表示で
各カテゴリは最大19件のためページ送りは不要。

【代表1件の選び方】
商品名の末尾に重量が入る(75g〜300g)。同じ銘柄が重量違いの別商品として並ぶものは
(「お得用250g」「Big Size 250g/400g/500g」)、最小重量の商品を代表とし、大容量側は
EXCLUDE_ITEM_IDSで除外する。ダークロースト版(別焙煎度、別ロット名)は別銘柄として残す。

【価格0円の商品】
「オリジナルブレンド ベリー・ベリー」(item/252)は価格が0円表示のため価格不明として収録しない。

【在庫】
商品ページに「カートに入れる」ボタン(addtocart())があるかどうかで判定する。
在庫欄が「在庫切れ」の商品はボタンが無く、販売終了ではなく品切れとして収録する。

【flavor_notes・精製】
商品説明に「生産処理：ウォッシュド」「品種：...」「風味属性：...」の定型行があるので、
風味属性をflavor_notes、生産処理をprocessing_methodに使う(商品名にも書かれている場合は名前優先)。
インフューズド(果実等を加える製法)は実データで該当なし(発酵カテゴリの商品は全て
コーヒーチェリー自体の発酵処理で、後添加の記述は無い)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "Aurora Coffee Roasters",
    "url": "https://www.auroracoffeeroasters.jp/",
    "platform": "独自EC(xaas3.jp)",
    "address": "岩手県岩手郡雫石町上野二ツ森2-2",
    "prefecture": "岩手県",
    "robots_txt_status": "許可(2026-10-13確認。/default/error/・/preview/のみDisallow)",
}

BASE_URL = "https://www.auroracoffeeroasters.jp"
CATEGORY_IDS = [2, 5, 6, 7, 11, 14, 15]
# 同一銘柄の大容量版(最小重量の商品を代表にするため除外): ダテーラ サンライズ250g/500g、
# チェルベサ ナチュラル250g、ハロベリティ ゼリフン250g、エスピリット・サント250g、
# ガトンボヤ ピーベリー250g、デカフェ ダテーラ400g
EXCLUDE_ITEM_IDS = {136, 304, 358, 362, 391, 394, 366}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

ITEM_URL_PATTERN = re.compile(r"/item/(\d+)/")
TITLE_PREFIX_PATTERN = re.compile(r"^.*?[❗⭐]️?\s*")
WEIGHT_PATTERN = re.compile(r"(?:お得用|お徳用)?\s*(\d{2,3})\s*[gｇ](?![a-zA-Z])")
PRICE_PATTERN = re.compile(r"([\d,]+)円")
PROCESS_LINE_PATTERN = re.compile(r"生産処理[：:]\s*([^\n]+)")
FLAVOR_LINE_PATTERN = re.compile(r"風味属性[：:]\s*([^\n]+)")


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_item_ids() -> list[int]:
    ids = []
    for cid in CATEGORY_IDS:
        text = fetch_text(f"{BASE_URL}/category/{cid}/")
        for i in ITEM_URL_PATTERN.findall(text):
            if int(i) not in ids:
                ids.append(int(i))
        time.sleep(CRAWL_DELAY_SECONDS)
    return ids


def clean_title(raw_title: str) -> tuple[str, int | None]:
    """販促プレフィックス(Recommended❗️等)と重量表記を取り除いた商品名と、最小の重量(g)を返す。"""
    title = TITLE_PREFIX_PATTERN.sub("", raw_title.strip())
    weights = [int(w) for w in WEIGHT_PATTERN.findall(title)]
    weight = min(weights) if weights else None
    title = WEIGHT_PATTERN.sub(" ", title)
    title = re.sub(r"[\s　]+", " ", title).strip(" ・")
    return title, weight


def fetch_detail(item_id: int) -> dict | None:
    url = f"{BASE_URL}/item/{item_id}/"
    html = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.select_one("#itemDetail01 h2")
    if not h2:
        return None
    raw_title = h2.get_text(strip=True)
    price_el = soup.select_one("li.sales_price span.data")
    price_m = PRICE_PATTERN.search(price_el.get_text(strip=True)) if price_el else None
    price = int(price_m.group(1).replace(",", "")) if price_m else None
    main = soup.select_one("div.mainTxt")
    desc = main.get_text("\n", strip=True) if main else ""
    return {
        "url": url,
        "raw_title": raw_title,
        "price": price,
        "in_stock": "addtocart()" in html,
        "description": desc,
    }


def build_record(detail: dict) -> dict | None:
    name, weight = clean_title(detail["raw_title"])
    if not detail["price"]:
        return None  # 価格0円・不明は収録しない

    parsed = parse_product(name)
    desc = detail["description"]

    proc_m = PROCESS_LINE_PATTERN.search(desc)
    processing = parsed["processing_method"]
    if not processing and proc_m:
        processing = normalize_processing_method(proc_m.group(1).strip())
    flavor_m = FLAVOR_LINE_PATTERN.search(desc)
    flavor_notes = flavor_m.group(1).strip() if flavor_m else None

    if parsed["category"] != "ブレンド":
        parsed = apply_category_hint_fallback(parsed, None)

    roast = parsed["roast_level"]
    if roast == "ハイロースト" and "ハイブリッド" in name:
        roast = None  # 「ハイブリッドウォッシュド」の「ハイ」をハイローストと誤検出するのを防ぐ
    if roast is None and re.search(r"ダークロースト|Dark Roast", name, re.I):
        roast = "ダークロースト"  # 店の表記どおり(パーサーに該当語なし)

    stock_status = detect_stock_status(name, not detail["in_stock"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": detail["url"],
    }


def scrape_all_products() -> list[dict]:
    ids = [i for i in collect_item_ids() if i not in EXCLUDE_ITEM_IDS]
    records = []
    for item_id in ids:
        try:
            detail = fetch_detail(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item/{item_id} ({e})")
            continue
        if detail is None:
            continue
        rec = build_record(detail)
        if rec is None:
            print(f"[skip] 価格不明のため除外: {detail['raw_title']}")
        else:
            records.append(rec)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": [],
        "non_bean_products_excluded": [],
    }
    with open("data_auroracoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_auroracoffeeroasters.json に出力しました")
