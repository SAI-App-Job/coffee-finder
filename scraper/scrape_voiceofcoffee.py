# -*- coding: utf-8 -*-
"""
scrape_voiceofcoffee.py

VOICE of COFFEE(shop.voiceofcoffee.com、兵庫県神戸市中央区栄町通3-1-17 ブレッシュ1F、
自家焙煎)の商品情報を取得する。カラーミーショップ(EUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(?mode=srh)44件のうち、「<銘柄>/<焙煎度> - 200g」
「... - 100g」の形で重量違いが別商品(別pid)として並ぶ豆商品(ブレンド3、シングル、カフェインレス)が
対象。同一銘柄は最小重量(100g)の商品を代表とする。コーヒーバッグ・リキッドコーヒー・マグカップ・
ギフト/トライアルセット・食器洗いクロスは除外。
在庫は一覧の「SOLD OUT」表示で判定する。価格は詳細ページのColorme JSON(税込)から取る。
"""

import json
import re
import time
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "VOICE of COFFEE",
    "url": "https://shop.voiceofcoffee.com/",
    "platform": "カラーミーショップ(shop-pro)",
    "address": "兵庫県神戸市中央区栄町通3-1-17 ブレッシュ1F",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://shop.voiceofcoffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["コーヒーバッグ", "リキッド", "マグカップ", "ギフト", "セット", "クロス", "トライアル", "ドリップバッグ"]
WEIGHT_SUFFIX = re.compile(r"\s*-\s*(\d+)\s*g\s*$")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
COLORME_JSON = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
LABELS = ("生産国", "地域", "農園名", "農園", "標高", "収穫", "精製", "品種", "生産者")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def list_items() -> list[dict]:
    items, page = [], 1
    while True:
        soup, _ = fetch(f"{BASE_URL}?mode=srh&keyword=&sort=n" + (f"&page={page}" if page > 1 else ""))
        units = soup.select("li.prd-lst-unit")
        if not units:
            break
        for u in units:
            a = u.select_one(".prd-lst-name a")
            if not a:
                continue
            title = re.sub(r"\s+", " ", a.get_text(strip=True)).strip()
            m = WEIGHT_SUFFIX.search(title)
            if not m or any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            exp = u.select_one(".prd-lst-exp")
            items.append({
                "name": WEIGHT_SUFFIX.sub("", title).strip(),
                "weight": int(m.group(1)),
                "href": a["href"],
                "sold_out": u.select_one(".prd-lst-soldout") is not None,
                "exp": exp.get_text(strip=True) if exp else None,
            })
        page += 1
        time.sleep(0.5)
    return items


def build_record(it: dict) -> dict:
    url = BASE_URL + it["href"].lstrip("/")
    soup, raw = fetch(url)
    price = None
    m = COLORME_JSON.search(raw)
    if m:
        try:
            prod = json.loads(m.group(1)).get("product", {})
            price = prod.get("sales_price_including_tax")
        except json.JSONDecodeError:
            pass
    exp_el = soup.select_one(".product-exp")
    text = exp_el.get_text("\n", strip=True) if exp_el else ""
    labels, intro = {}, []
    for ln in text.split("\n"):
        mm = re.match(r"^(%s)\s*[：:]\s*(.+)$" % "|".join(LABELS), ln.strip())
        if mm:
            labels[mm.group(1)] = mm.group(2).strip()
        else:
            intro.append(ln.strip())

    name = it["name"]
    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and labels.get("生産国"):
            c = detect_country_name(labels["生産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and labels.get("精製"):
            processing = normalize_processing_method(labels["精製"])
    hint = ROAST_HINT_PATTERN.search(name)
    farm_bits = [f"{k}: {labels[k]}" for k in ("地域", "農園名", "標高", "品種") if labels.get(k)]
    notes = " ".join(x for x in [it["exp"]] + intro[:2] if x)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": hint.group(1) if hint else None,
        "flavor_notes": notes[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    groups = OrderedDict()
    for it in list_items():
        cur = groups.get(it["name"])
        if cur is None or it["weight"] < cur["weight"]:
            groups[it["name"]] = it
    records = []
    for it in groups.values():
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['href']} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_voiceofcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_voiceofcoffee.json に出力しました")


if __name__ == "__main__":
    main()
