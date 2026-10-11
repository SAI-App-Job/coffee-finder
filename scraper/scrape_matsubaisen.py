# -*- coding: utf-8 -*-
"""
scrape_matsubaisen.py

松焙煎店(コーヒーロースト松焙煎店、matsubaisen.official.ec、公式 m-baisen.com、
奈良県奈良市北風呂町20-2)の焙煎豆を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-11): sitemap.xml の全25商品のうち、ドリップバッグ(156421516)を除く
24銘柄(いずれも「焙煎後約200g」表記・焙煎度は購入時に選択する「おまかせ焙煎度」)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得し、
焙煎度は説明文の「◆おまかせ焙煎度:」の記載(H=中煎り、C=中深煎り、FC/FC強=深煎り)を採用する。
産地は説明文・カテゴリ(中米・カリブ/南米/アジア・オセアニア/アフリカ)から確認できるものだけを
ORIGINSに明示し、確認できないもの(エーデルワイス)は null。
"""
import json
import re

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "松焙煎店",
    "url": "https://matsubaisen.official.ec/",
    "platform": "BASE",
    "address": "奈良県奈良市北風呂町20-2",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}
BASE_URL = "https://matsubaisen.official.ec"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_G = 200
EXCLUDE_IDS = {"156421516"}  # ドリップバッグコーヒー

# 商品ID: (産地, 分類)  分類: ストレート/ブレンド/デカフェ
ORIGINS = {
    "146680831": ("ブラジル", "ストレート"),
    "146680832": ("コロンビア", "ストレート"),
    "146680835": ("グアテマラ", "ストレート"),
    "146680838": ("エチオピア", "ストレート"),
    "146680840": ("インドネシア", "ストレート"),
    "146680845": ("ブラジル", "ストレート"),
    "146680847": ("コロンビア", "ストレート"),
    "146680853": (None, "ストレート"),
    "146680854": ("インドネシア", "ストレート"),
    "146680856": ("ジャマイカ", "ストレート"),
    "146680858": ("ブラジル", "デカフェ"),
    "146680860": ("コロンビア", "デカフェ"),
    "146680862": ("エチオピア", "ストレート"),
    "146680866": ("タンザニア", "ストレート"),
    "146680870": ("ケニア", "ストレート"),
    "146680874": ("メキシコ", "ストレート"),
    "146680880": ("ブラジル", "ストレート"),
    "146680883": (None, "ブレンド"),
    "146680884": (None, "ブレンド"),
    "147529125": ("パプアニューギニア", "ストレート"),
    "151758151": ("コスタリカ", "ストレート"),
    "155082060": ("ボリビア", "ストレート"),
    "156420672": ("イエメン", "ストレート"),
    "157499495": ("コロンビア", "ストレート"),
}
ROAST_MAP = {"M": "中浅煎り", "H": "中煎り", "C": "中深煎り", "FC": "深煎り", "FC強": "深煎り"}

TITLE_RE = re.compile(r'og:title" content="([^"]*)"')
DESC_RE = re.compile(r'og:description" content="([^"]*)"')
PRICE_RE = re.compile(r'product:price:amount" content="(\d+)"')
PURCH_RE = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_RE = re.compile(r"おまかせ焙煎度[：:]\s*(FC強|FC|H|C|M)")


def clean_name(title: str) -> str:
    t = title.split("|")[0].replace("　", " ")
    t = re.sub(r"焙煎後約\d+g", "", t)
    t = re.sub(r"^【数量限定】", "", t)
    return re.sub(r"\s+", " ", t).strip()


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=HEADERS, timeout=30)
    resp.encoding = "utf-8"
    t = resp.text
    import html as _h
    title = _h.unescape(TITLE_RE.search(t).group(1))
    name = clean_name(title)
    dm = DESC_RE.search(t)
    desc_full = _h.unescape(dm.group(1)) if dm else ""
    desc = re.sub(r"\s+", " ", desc_full).strip()[:400] or None
    pm = PRICE_RE.search(t)
    pu = PURCH_RE.search(t)
    sold_out = bool(pu) and pu.group(1) == "unpurchasable"
    rm = ROAST_RE.search(desc_full)
    roast = ROAST_MAP[rm.group(1)] if rm else None
    origin, category = ORIGINS[item_id]
    parsed = parse_product(name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": "raw_name" if origin else None,
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(pm.group(1)) if pm else None,
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    sm = requests.get(f"{BASE_URL}/sitemap.xml", headers=HEADERS, timeout=30).text
    ids = sorted(set(re.findall(r"/items/(\d+)", sm)) - EXCLUDE_IDS)
    records = []
    for item_id in ids:
        if item_id not in ORIGINS:
            print(f"[warn] 未知の商品ID(要確認): {item_id}")
            continue
        try:
            records.append(build_record(item_id))
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    with open("data_matsubaisen.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsubaisen.json に出力しました")


if __name__ == "__main__":
    main()
