# -*- coding: utf-8 -*-
"""
scrape_bastetcoffee.py

BASTET COFFEE(https://bastetcoffee.com/、京都府京都市左京区一乗寺大原田町23-11)の商品情報を
取得する。Shopify(/products.json)。

【対象商品について】
実データ確認済み(2026-10-21): `/products.json`のうちproduct_typeが「コーヒー豆」の商品から、
次を除いた豆(シングルオリジン・ブレンド・デカフェ)を対象とする。
 - SCAJ招待券チケット、「3匹の…」飲み比べ3種セット、トライアルセット
 - インフューズド/共発酵(果実・花・香料を加える製法): ピーチ共発酵、スイカ、ラベンダードライ、
   イエローフルーツ(ネクター共発酵)、ライチ/ストロベリー/パッションフルーツのインフューズドハニー
   (商品説明の Process 欄・本文で「共発酵」「インフューズド」「果実/花を加える」と明記されたもの)
 - ドリップバッグ・グッズ・器具・定期便・ケーキ(product_typeが「コーヒー豆」以外)
バリエーションは「豆のまま」を対象に、50g以上で最小の重量(多くは100g、希少ゲイシャは50g)の価格を
代表とする(15g・30gの試飲小分けは採らない)。売り切れの過去ロットも完売として登録する。
産地は商品説明冒頭の英語国名表記(例: COLOMBIA ...)、焙煎度は説明内の「Roast:」欄、
精製方法は「Process:」欄から取得する。
"""

import json
import os
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "BASTET COFFEE",
    "url": "https://bastetcoffee.com/",
    "platform": "Shopify",
    "address": "京都府京都市左京区一乗寺大原田町23-11",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10-21確認。Shopify標準のrobots.txtで/products.jsonは禁止されていない)",
    "source_note": "公式Shopify https://bastetcoffee.com/products.json(コーヒー豆カテゴリ)を2026-10-21に確認。住所は https://bastetcoffee.com/policies/legal-notice の所在地。自家焙煎の根拠は /pages/bastet-coffeeの焙煎について(台湾から取り寄せた焙煎機)。商品最終更新2026-10-21。インフューズド・共発酵7点、セット、チケットは除外",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://bastetcoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
BEAN_TYPE = "コーヒー豆"
MIN_SAMPLE_WEIGHT = 50  # これ未満(15g・30g)の試飲小分けは代表にしない

# 除外するハンドル(セット・チケット・インフューズド/共発酵)
EXCLUDE_HANDLES = {
    "scaj2026-ticket",
    "3-unique-geisha", "3-top-geisha", "3-ethiopians-2", "3-blend",
    "trialset",
    "colombia-lospatios-geisha-peach",        # ピーチ共発酵
    "colombia-geisha-watermelon",             # スイカ共発酵(カルチャリング)
    "colombia-losnogales-lavender",           # ラベンダードライ(インフューズド)
    "colombia-elmirador-yellowfruits",        # イエローフルーツ ネクター共発酵
    "colombia-lychee",                        # ライチインフューズドハニー
    "colombia-strawberry",                    # ストロベリーインフューズドハニー
    "colombia-passionfruit",                  # パッションフルーツインフューズドハニー
}

# ハンドル(商品URL)に含まれる国名表記 → 産地(商品名は農園名のみで国名を含まないため、ハンドルを最優先で使う)
HANDLE_COUNTRIES = [
    ("yunnan", "中国"), ("ethiopia", "エチオピア"), ("brazil", "ブラジル"), ("colombia", "コロンビア"),
    ("guatemala", "グアテマラ"), ("costarica", "コスタリカ"), ("elsalvador", "エルサルバドル"),
    ("panama", "パナマ"), ("kenya", "ケニア"), ("rwanda", "ルワンダ"), ("peru", "ペルー"),
    ("nicaragua", "ニカラグア"), ("honduras", "ホンジュラス"), ("indonesia", "インドネシア"),
]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\b")
MULTI_PATTERN = re.compile(r"[x×]\s*\d")
ROAST_MAP = {"light": "浅煎り", "medium-light": "中浅煎り", "medium": "中煎り", "medium-dark": "中深煎り", "dark": "深煎り"}


def fetch_products() -> list[dict]:
    # 環境変数 PRODUCTS_JSON_FILE が指定されていれば、事前に取得済みの /products.json を読む
    # (サイト側が429を返し続ける場合に、過去に取得したスナップショットから生成するため)
    snapshot = os.environ.get("PRODUCTS_JSON_FILE")
    if snapshot:
        with open(snapshot, encoding="utf-8") as f:
            return json.load(f).get("products", [])
    products = []
    page = 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return products


def pick_variant(p: dict):
    candidates = []
    for v in p["variants"]:
        t = v.get("title") or ""
        if "豆のまま" not in t:
            continue
        if MULTI_PATTERN.search(t):
            continue
        m = WEIGHT_PATTERN.search(t)
        if m:
            candidates.append((int(m.group(1)), v))
    if not candidates:
        return None, None
    normal = [c for c in candidates if c[0] >= MIN_SAMPLE_WEIGHT]
    pool = normal or candidates
    weight = min(w for w, _ in pool)
    vs = [v for w, v in pool if w == weight]
    return weight, vs[0]


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        if p.get("product_type") != BEAN_TYPE or p["handle"] in EXCLUDE_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        weight, variant = pick_variant(p)
        if variant is None or not float(variant["price"]):
            print(f"[skip] 重量・価格が取れない: {p['handle']}")
            continue

        text = re.sub(r"\s+", " ", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        notes_m = re.search(r"Notes:\s*(.*?)\s*(?:Awards:|About the CAT|$)", text)
        desc = (notes_m.group(1) if notes_m else text)[:400] or None
        roast_m = re.search(r"Roast:\s*([A-Za-z\-]+)", text)
        roast = ROAST_MAP.get(roast_m.group(1).lower()) if roast_m else None
        process_m = re.search(r"Process:\s*(.*?)\s*(?:Altitude:|Roast:|Notes:|Awards:|About the CAT)", text)

        parsed = parse_product(title)
        is_blend = parsed["category"] == "ブレンド"

        origin = None
        origin_source = None
        if not is_blend:
            for kw, c in HANDLE_COUNTRIES:
                if kw in p["handle"]:
                    origin = c
                    break
            if not origin:
                origin = parsed["origin_country"] or detect_country_name(text[:80])
            origin_source = "description" if origin else None
        processing = parsed["processing_method"]
        if not processing and process_m:
            processing = parse_product(process_m.group(1))["processing_method"]

        available = bool(variant.get("available"))
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": origin,
            "origin_source": origin_source,
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bastetcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bastetcoffee.json に出力しました")


if __name__ == "__main__":
    main()
