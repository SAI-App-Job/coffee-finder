# -*- coding: utf-8 -*-
"""
scrape_annycoffee.py

Anny coffee(annycoffee.shop-pro.jp、カラーミーショップ)の商品情報を取得する。
静岡県浜松市中央区中野町17-1(特定商取引法表記で確認)。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全8商品(100g 6点、200g 2点)。同一銘柄が100gと200gで別商品に
なっているもの(カフェオルキデア、アイスコーヒー用カフェオルキデア)は最小重量の100gを代表とし、
200gは除外した。結果、6銘柄(ネコポス限定100g: デカフェ・ピーベリー・ベレテゲラ・
カフェオルキデア・マヤビニック、アイスコーヒー用カフェオルキデア)を対象とする。

【文字コード】EUC-JP(実データ確認済み)。

【商品説明の構造】
div.product-order-exp 内に「《中深煎り》」(焙煎度)、紹介文、「【生産地域】【品種】【栽培方法】
【精選方法】」が定型で入っている(実データ確認済み)。焙煎度・産地・精選方法はここから取得する。
「アイスコーヒー用カフェオルキデア」は《深煎り》表記だが紹介文に「中深煎りで仕上げています」と
あり表記が揺れている。ページ冒頭の《》表記を優先して採用する。

【価格・重量・在庫】
バリアントは「豆」「粉」で価格は同額。「豆」の税込価格を採用する。重量は商品名の【100g】。
在庫は一覧・詳細に品切れ表示が無く(実データ確認済み)、stock_numもNoneのため、
「SOLD OUT」「売り切れ」の文言があれば完売とし、無ければ販売中とする。

【robots.txtについて】
shop-pro.jp の他店舗と同一の記述(/secure/ 等のみ制限)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "Anny coffee",
    "url": "https://annycoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "静岡県浜松市中央区中野町17-1",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(shop-pro.jp共通。/secure/等以外は制限なし。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://annycoffee.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# 対象の100g商品(200gの同一銘柄は最小重量の100gを代表にするため除外)
TARGET_PIDS = [
    "149963736",  # デカフェ
    "149963717",  # ピーベリー
    "149963694",  # ベレテゲラ
    "149963616",  # カフェオルキデア
    "149963370",  # マヤビニック
    "149963811",  # アイスコーヒー用カフェオルキデア
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"[【\[](\d+)\s*[gｇ][】\]]")
ROAST_PATTERN = re.compile(r"《(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)》")
LABEL_PATTERN = re.compile(r"【(生産地域|品種|栽培方法|精選方法)】\s*([^\n【]+)")


def fetch(url: str) -> str:
    last = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "euc-jp"
            return resp.text
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def clean_name(title: str) -> str:
    """《ネコポス限定》・【100g】・末尾のキャッチコピーを除いた銘柄名にする。"""
    name = re.sub(r"《[^》]*》", "", title)
    name = re.split(r"[【\[]\d+\s*[gｇ][】\]]", name)[0]
    return name.strip()


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = (product.get("name") or "").strip()

    soup = BeautifulSoup(html_text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    exp_el = soup.select_one("div.product-order-exp")
    exp_text = exp_el.get_text("\n", strip=True) if exp_el else ""

    roast_m = ROAST_PATTERN.search(exp_text)
    labels = {k: v.strip() for k, v in LABEL_PATTERN.findall(exp_text)}
    # 紹介文: 《焙煎度》の次の行から【生産地域】の手前まで
    intro = None
    if roast_m:
        body = exp_text[roast_m.end():].split("【生産地域】")[0]
        intro = re.sub(r"\s+", " ", body).strip()[:400] or None

    name = clean_name(title)
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if labels.get("生産地域"):
        country = detect_country_name(labels["生産地域"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)
    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    weight_m = WEIGHT_PATTERN.search(title)
    variants = product.get("variants", [])
    bean_variant = next((v for v in variants if (v.get("option1_value") or "") == "豆"), variants[0] if variants else None)
    price = bean_variant.get("option_price_including_tax") if bean_variant else product.get("sales_price_including_tax")

    stock_num = product.get("stock_num")
    page_text = soup.get_text(" ", strip=True)
    sold_out = (isinstance(stock_num, int) and stock_num <= 0) or bool(re.search(r"SOLD\s*OUT|売り切れ", page_text, re.I))

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産地域", "品種", "栽培方法") if labels.get(k)]

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
        "flavor_notes": intro,
        "farm_note": "、".join(farm_parts) if farm_parts else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in TARGET_PIDS:
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_annycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_annycoffee.json に出力しました")


if __name__ == "__main__":
    main()
