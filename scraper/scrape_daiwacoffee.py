# -*- coding: utf-8 -*-
"""
scrape_daiwacoffee.py

ダイワ珈琲(www.daiwacoffee.jp、愛知県名古屋市北区天道町5-4-1)の商品情報を取得する。
おちゃのこネット(Ocnk)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品(103件)のうち、豆のカテゴリ
「全商品(ブレンディング)」(product-list/1)・「全商品(スペシャルクラス)」(62)・
「全商品(深煎りシングル)」(80)・「デカフェ(カフェインレス)/オーガニック」(96)・
「品評会受賞/トップオブトップロット」(36)の計80件(重量違いの別商品として並ぶ)を、
銘柄ごとに最小重量の商品を代表として採用する(重量は商品名末尾の「200g」「250g」「100g」「50g」等)。
ツール(ペーパードリップ・ネルドリップ)、価格・重量の無い「【間もなく発売!】ケニヤ・ケグワAA」
(未発売)、「業務店オリジナルブレンドコーヒー」(業務用・価格なし)は除外。
同一銘柄の重量違い商品は別pidのため、代表商品のURLを採用し、product_urlは銘柄ごとに一意。

【ページ構造について】
一覧の`li.list_item_cell`内の`data-product-id`・`.goods_name`・`.selling_price .figure`(税込)・
`p.stock`(在庫あり/在庫わずか/在庫なし)を使う。在庫なしは完売、在庫わずかは販売中扱い。
商品ページの`div.item_desc_text`が説明文。ブレンドはcategory 1、それ以外はシングル。
デカフェは説明文の「デカフェプロセス:マウンテンウォーター製法」を採用する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "ダイワ珈琲",
    "url": "https://www.daiwacoffee.jp/",
    "platform": "おちゃのこネット",
    "address": "愛知県名古屋市北区天道町5-4-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Ocnk標準構成)",
}

BASE_URL = "https://www.daiwacoffee.jp"
CATEGORIES = [("1", "blend"), ("62", "single"), ("80", "single"), ("96", "single"), ("36", "single")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 12

NAME_PATTERN = re.compile(r"^(.+?)\s*(\d+(?:\.\d+)?)\s*(kg|g)(?:\s*[(（].*[)）])?\s*$", re.I)
ROAST_PATTERN = re.compile(
    r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ロースト|(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
# coffee_parserの国名辞書に無い、店舗側の表記ゆれ
COUNTRY_TYPOS = {"ホンジュス": "ホンジュラス"}
DESC_NOISE_PATTERN = re.compile(r"【(?:Co-op|Farmers|Location|Process|Variety|Altitude)】")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/product-list/{cat_id}" + ("" if page == 1 else f"?page={page}")
            soup = BeautifulSoup(fetch_html(url), "html.parser")
            new = 0
            for cell in soup.select("li.list_item_cell"):
                d = cell.select_one("[data-product-id]")
                name_el = cell.select_one(".goods_name")
                if not (d and name_el):
                    continue
                pid = d["data-product-id"]
                if pid in items:
                    continue
                new += 1
                price_el = cell.select_one(".selling_price .figure")
                pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
                stock_el = cell.select_one("p.stock")
                items[pid] = {
                    "pid": pid,
                    "name": re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "stock_text": stock_el.get_text(strip=True) if stock_el else "",
                    "group": group,
                }
            if new == 0:
                break
    return list(items.values())


def split_name(name: str) -> dict | None:
    m = NAME_PATTERN.match(unicodedata.normalize("NFKC", name))
    if not m:
        return None
    base = re.sub(r"\s+", " ", m.group(1)).strip()
    weight = int(float(m.group(2)) * (1000 if m.group(3).lower() == "kg" else 1))
    return {"base": base, "weight": weight, "key": base.replace(" ", "")}


def fetch_description(pid: str) -> str | None:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    el = soup.select_one("div.item_desc_text")
    return el.get_text("\n", strip=True) if el else None


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[int, dict, dict]] = {}
    for item in list_items():
        parts = split_name(item["name"])
        if not parts or item["price"] is None:
            continue
        cand = (parts["weight"], item, parts)
        cur = best.get(parts["key"])
        if cur is None or cand[0] < cur[0]:
            best[parts["key"]] = cand

    records = []
    for weight, item, parts in best.values():
        base = parts["base"]
        full_desc = fetch_description(item["pid"]) or ""
        desc = re.sub(r"\s+", " ", full_desc).strip()[:400] or None

        parsed = parse_product(base)
        is_blend = item["group"] == "blend"
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                for typo, country in COUNTRY_TYPOS.items():
                    if typo in base:
                        parsed["origin_country"] = country
                        parsed["origin_source"] = "raw_name"
                        break
            if not parsed["origin_country"]:
                c = detect_country_name(base)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, base)

        processing = parsed["processing_method"]
        if not is_blend and not processing:
            pm = re.search(r"【Process】\s*([^\n【]+)", full_desc)
            processing = detect_processing_method(pm.group(1)) if pm else None
        if is_blend:
            processing = None

        rm = ROAST_PATTERN.search(base) or ROAST_PATTERN.search(full_desc)
        roast = rm.group(0) if rm else None

        decaf_process = None
        if re.search(r"デカフェ|カフェインレス", base):
            dm = re.search(r"デカフェプロセス\s*[：:]\s*([^\n]+)", full_desc)
            if dm and "マウンテンウォーター" in dm.group(1):
                decaf_process = "マウンテンウォータープロセスによりカフェインを除去"
            elif dm and "スイスウォーター" in dm.group(1):
                decaf_process = "スイスウォータープロセスによりカフェインを除去"

        sold_out = "在庫なし" in item["stock_text"]
        record = {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        }
        if decaf_process:
            record["decaf_process"] = decaf_process
        records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_daiwacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_daiwacoffee.json に出力しました")


if __name__ == "__main__":
    main()
