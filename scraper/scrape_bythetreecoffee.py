# -*- coding: utf-8 -*-
"""
scrape_bythetreecoffee.py

BY THE TREE COFFEE(bythetree.base.shop、鹿児島県奄美市名瀬幸町4-1 1F)の商品情報を取得する。BASE。
BASEのrobots.txtは python-requests/curl 等を個別にDisallowしているため、識別可能な独自User-Agentを使い、
リクエスト間隔は5秒以上空ける。

【対象商品】全10商品のうちコーヒー豆7銘柄(ブレンド1+シングル6、うちデカフェ1、完売2)。Tシャツ・ステッカー2種は除外。
重量・焙煎度・精製・フレーバーは商品説明(og:description)の「内容量」「Roast [焙煎]」「Process [精製方法]」「Flavor Notes」から取る。
ゲラ(Anaerobic Natural)・カルマチ(Carbonic Maceration)・ラ・ルクマ(Anaerobic washed)は発酵系の精製方法だが、
果実やハーブを加えるインフューズドではないため登録する。ラ・ルクマのみ150g(100g版なし)。
完売(SOLD OUT)の2銘柄は在庫「完売」として登録する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, detect_processing_method

SHOP_INFO = {
    "name": "BY THE TREE COFFEE",
    "url": "https://bythetree.base.shop/",
    "platform": "BASE",
    "address": "鹿児島県奄美市名瀬幸町4-1 1F",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-11確認。python-requests/curl等は個別にDisallow、User-agent: * は/cart/等以外許可。識別可能なUser-Agentを使用)",
    "source_note": "公式 https://www.bythetreecoffee.com ・販売 https://bythetree.base.shop/ ・/about ・特商法 /law を2026-11-02に確認。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://bythetree.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5.5

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")

# (商品ID, 商品名, 分類, 産地)
ITEMS = [
    ("74556086", "BTTC BLEND", "ブレンド", None),
    ("123010588", "El Diamante - Honduras", "ストレート", "ホンジュラス"),
    ("86107940", "Gera - ETHIOPIA [Anaerobic Natural]", "ストレート", "エチオピア"),
    ("79285056", "Decaf / Sidamo - ETHIOPIA", "デカフェ", "エチオピア"),
    ("79258587", "La Folie - GUATEMALA", "ストレート", "グアテマラ"),
    ("89510186", "Karmachi - ETHIOPIA", "ストレート", "エチオピア"),
    ("83718358", "La Lucuma - PERU", "ストレート", "ペルー"),
]

ROAST_MAP = {"中浅煎り": "中浅煎り", "浅煎": "浅煎り","浅煎り": "浅煎り", "中煎り": "中煎り", "中深煎り": "中深煎り", "深煎り": "深煎り"}
PROCESS_MAP = {
    "carbonic maceration": "カーボニックマセレーション",
    "anaerobic washed": "アナエロビック",
    "anaerobic natural": "アナエロビック",
}


ROAST_PATTERN = re.compile(r"Roast\s*(?:\[焙煎\])?\s*[:：]\s*(中深煎り|中浅煎り|浅煎り|浅煎|中煎り|深煎り)")


def field(desc: str, label: str) -> str | None:
    """og:descriptionは改行が潰れて値の直後に次の項目(日本語の説明文等)が続くため、日本語文字の手前で打ち切る。"""
    m = re.search(label + r"\s*[:：]\s*([^\n]+)", desc)
    if not m:
        return None
    return re.split(r"[぀-ヿ一-鿿]", m.group(1))[0].strip() or None


def build_record(item_id: str, name: str, category: str, origin: str | None) -> dict:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = resp.text
    desc_m = DESC_PATTERN.search(text)
    desc = html.unescape(desc_m.group(1)) if desc_m else ""
    price_m = PRICE_PATTERN.search(text)
    pur_m = PURCHASABILITY_PATTERN.search(text)
    sold_out = bool(pur_m) and pur_m.group(1) == "unpurchasable"

    wm = re.search(r"内容量\s*[:：]\s*(\d+)\s*g", desc)
    rm = ROAST_PATTERN.search(desc)
    roast = ROAST_MAP.get(rm.group(1)) if rm else None
    notes = field(desc, r"Flavor Notes?")
    proc_raw = field(desc, r"Process\s*\[精製方法\]")
    processing = None
    if proc_raw:
        low = proc_raw.lower()
        processing = next((v for k, v in PROCESS_MAP.items() if k in low), None) or detect_processing_method(proc_raw)
        if "mountain water" in low:
            processing = "マウンテンウォータープロセス(デカフェ用)"
    parsed = parse_product(name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": None if category == "ブレンド" else origin,
        "origin_source": None if category == "ブレンド" else "raw_name",
        "designated_brand": None,
        "processing_method": processing,
        "grade": None,
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": int(wm.group(1)) if wm else None,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, cat, origin in ITEMS:
        try:
            records.append(build_record(item_id, name, cat, origin))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    with open("data_bythetreecoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bythetreecoffee.json に出力しました")


if __name__ == "__main__":
    main()
