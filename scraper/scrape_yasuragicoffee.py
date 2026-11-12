# -*- coding: utf-8 -*-
"""
scrape_yasuragicoffee.py

自家焙煎珈琲やすらぎ(yasuragi-coffee.jp、大阪府泉佐野市市場西1-1-10、受注後焙煎、店頭受け取り可)の
通販サイトから珈琲豆の商品情報を取得する。ショップサーブ(cart9.shopserve.jp/-/yasuragi-coffee.jp)。
robots.txt は Disallow 空(全許可)。ページは実測で UTF-8(meta charset=UTF-8)。間隔は2秒。

【取得方法】トップページの商品リンクから /SHOP/(BC|SC)xx-xxxx.html を集め、各商品ページの
ld+json(ProductGroup、hasVariant に豆の状態×小分け×発送方法の全組み合わせ)の最小価格を採用する
(豆のまま・挽き目違いは同価格)。品番末尾 0100 は「100g単位」商品(100g=1単位の価格)、
0200 は「200gまたは500g単位」商品(200gの価格を採用)。

【除外】飲み比べセット・ギフト・業務用1KG(BC06/BC07/SC13)・水出しバッグ・器具・ラッピング、
および複数銘柄が1ページに載る「コーヒー豆探訪」(SC21、価格・銘柄の対応が特定できない)。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "自家焙煎珈琲やすらぎ",
    "url": "https://www.yasuragi-coffee.jp/",
    "platform": "ショップサーブ",
    "address": "大阪府泉佐野市市場西1-1-10",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(Disallow空)",
    "source_note": "公式 https://www.yasuragi-coffee.jp/ と各商品ページ(/SHOP/BCxx-0100.html 等)、特商法 /hpgen/HPB/shop/business.html を2026-10-26に確認。受注後焙煎・店頭受け取り可。コーヒー豆探訪は2025年産COE等の新ロットで更新は新しい。",
    "last_verified_at": "2026-10-26",
}

BASE = "https://www.yasuragi-coffee.jp"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 2.0
EXCLUDE_WORDS = ("業務用", "セット", "ギフト", "水出し", "探訪", "ラッピング", "キット", "ドリップ")
ROAST_MAP = [
    ("極深煎り", "極深煎り"), ("中深煎り", "中深煎り"), ("中浅煎り", "中浅煎り"), ("浅煎り", "浅煎り"),
    ("中煎り", "中煎り"), ("深煎り", "深煎り"),
    ("フレンチ", "極深煎り"), ("フルシティ", "深煎り"), ("シティ", "中深煎り"), ("ハイ", "中煎り"),
]


def get(url: str) -> str:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def collect_codes() -> list[tuple[str, str]]:
    soup = BeautifulSoup(get(BASE + "/"), "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"/SHOP/((?:BC|SC)\d+-\d+)\.html$", a["href"])
        if not m:
            continue
        text = a.get_text(" ", strip=True)
        if text and m.group(1) not in found:
            found[m.group(1)] = text
        elif m.group(1) not in found:
            found.setdefault(m.group(1), "")
    return [(c, t) for c, t in found.items() if not any(w in t for w in EXCLUDE_WORDS)]


def clean_name(n: str) -> str:
    n = html.unescape(n)
    n = re.sub(r"\[\s*受注後焙煎\s*\]", "", n)
    n = re.sub(r"【ゆうパケット可[^】]*】", "", n)
    n = re.sub(r"[（(]\s*\d+\s*[gｇG]\s*単位\s*[)）]", "", n)
    n = re.sub(r"[（(]\s*200ｇまたは500\s*[gｇ]\s*単位\s*[)）]", "", n)
    n = n.replace("【More Good Coffee】", "").replace("　", " ")
    return re.sub(r"\s+", " ", n).strip()


def normalize_roast(label: str) -> str | None:
    for key, val in ROAST_MAP:
        if key in label:
            return val
    return None


def build_record(code: str) -> dict | None:
    url = f"{BASE}/SHOP/{code}.html"
    soup = BeautifulSoup(get(url), "html.parser")
    tag = soup.find("script", type="application/ld+json")
    if not tag or not tag.string:
        return None
    ld = json.loads(tag.string, strict=False)
    pg = ld[0] if isinstance(ld, list) else ld
    raw = pg.get("name", "")
    if any(w in raw for w in EXCLUDE_WORDS):
        return None
    offers = [v.get("offers") or {} for v in pg.get("hasVariant") or []]
    prices = [int(float(o["price"])) for o in offers if o.get("price") is not None]
    if not prices:
        return None
    in_stock = any(o.get("availability") == "http://schema.org/InStock" for o in offers)
    name = clean_name(raw)
    if re.search(r"200\s*[gｇ]\s*または", raw):
        weight = 200
    else:
        wm = re.search(r"(\d+)\s*[gｇG]\s*単位", raw)
        weight = int(wm.group(1)) if wm else None
    text = soup.get_text("\n", strip=True)
    rm = re.search(r"([^\n／]+)／豆のまま", text)
    roast = normalize_roast(rm.group(1)) if rm else None
    is_blend = code.startswith("BC")
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            for kw, c in (("モカ", "エチオピア"), ("アマレロ", "ブラジル"), ("ガテマラ", "グアテマラ"), ("アロマ ショコラ", "ブラジル")):
                if kw in name:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
                    break
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": min(prices),
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code, _ in collect_codes():
        rec = build_record(code)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_yasuragicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yasuragicoffee.json に出力しました")


if __name__ == "__main__":
    main()
