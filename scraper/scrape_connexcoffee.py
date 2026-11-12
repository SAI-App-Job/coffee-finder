# -*- coding: utf-8 -*-
"""
scrape_connexcoffee.py

connex coffee(コネックスコーヒー、長野県安曇野市穂高北穂高2918-1、公式 connexcoffee.net、
「安曇野にある自家焙煎コーヒーとパブロバのお店」Roastery & Cafe)のオンラインショップ
(connexcoffee.net/shop/、WordPress + WooCommerce)の商品情報を取得する。

【robots.txt】https://connexcoffee.net/robots.txt は Disallow: /wp-admin/ のみ(2026-10-26確認)で、
WooCommerce Store API(/shop/wp-json/wc/store/v1/products)は禁止されていないため利用する。
【対象】カテゴリ BEANS のうち、ドリップバッグ・お試し飲み比べセットを除く単品の焙煎豆。
各商品は「状態(豆/粉/ドリップバッグ)×容量(150g/250g/4個セット)」のバリエーション式で、
豆(または状態未指定)の最小容量(150g。カメルーン・ロブスタは単品50g)の価格を採用する
(バリエーションごとの価格はStore APIの商品ID指定で取得)。
【産地・焙煎度・精製】各商品ページの「産地情報」表(味わい/焙煎度/地域/農園/精製方法/品種/標高)から取得。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method

SHOP_INFO = {
    "name": "connex coffee",
    "url": "https://connexcoffee.net/shop/",
    "platform": "WordPress + WooCommerce",
    "address": "長野県安曇野市穂高北穂高2918-1",
    "prefecture": "長野県",
    "robots_txt_status": "許可(2026-10-26確認。/wp-admin/のみDisallow。Store APIは禁止されていない)",
    "source_note": "公式オンラインショップ(https://connexcoffee.net/shop/)のWooCommerce Store APIと各商品ページを2026-10-26に確認。"
                   "トップ(https://www.connexcoffee.net/)に「安曇野にある自家焙煎コーヒーとパブロバのお店」「自家焙煎のスペシャルティコーヒーとパブロバを楽しめるRoastery＆Cafe」、"
                   "住所は同フッター。ニュース「自家焙煎豆の販売を開始」(2025-07-12)。トップのお知らせは2026-09-26まで更新されており新しい。"
                   "ドリップバッグ・お試し飲み比べセット・器具・ドリンク・雑貨は除外。",
    "last_verified_at": "2026-10-26",
}

API = "https://connexcoffee.net/shop/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2
NON_BEAN = ("ドリップバッグ", "セット")


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=30, **kw)
    r.raise_for_status()
    time.sleep(DELAY)
    return r


def weight_of(text):
    m = re.search(r"(\d+)\s*g", text or "", re.I)
    return int(m.group(1)) if m else None


def pick_variation(p):
    """豆(または状態未指定)の最小容量のバリエーションを返す: (variation_id, weight)"""
    cands = []
    for v in p.get("variations") or []:
        attrs = {a["name"]: a["value"] for a in v["attributes"]}
        if attrs.get("状態") not in ("bean", None):
            continue
        w = weight_of(attrs.get("容量"))
        if w:
            cands.append((w, v["id"]))
    return min(cands) if cands else None


def info_table(url):
    soup = BeautifulSoup(get(url).text, "html.parser")
    title = soup.title.string if soup.title else ""
    info = {}
    for tb in soup.select("table"):
        rows = tb.select("tr")
        for tr in rows:
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                info[th.get_text(strip=True)] = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
    return title, info


def build_record(p):
    name = re.sub(r"\s*\d+\s*g\s*$", "", html.unescape(p["name"]), flags=re.I).strip()
    price, weight, in_stock = None, None, bool(p.get("is_in_stock"))
    if p.get("type") == "variable":
        pv = pick_variation(p)
        if not pv:
            return None
        weight, vid = pv
        v = get(f"{API}/{vid}").json()
        price = int(v["prices"]["price"])
        in_stock = bool(v.get("is_in_stock"))
    else:
        price = int(p["prices"]["price"])
        weight = weight_of(p["name"]) or next(
            (weight_of(t["name"]) for a in p.get("attributes") or [] if a["name"] == "容量" for t in a["terms"]), None)
    title, info = info_table(p["permalink"])
    desc = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
    parsed = parse_product(name)
    parsed["category"] = "ストレート"
    parsed = apply_category_hint_fallback(parsed, name)
    if info.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(info["精製方法"])
    farm = [f"{k}: {info[k]}" for k in ("地域", "農園", "生産者", "品種", "標高") if info.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": info.get("焙煎度"),
        "flavor_notes": info.get("味わい") or desc[:300] or None,
        "farm_note": "、".join(farm) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "一時的に品切れ",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def scrape_all_products():
    products = get(API, params={"per_page": 100}).json()
    records = []
    for p in products:
        cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
        if "BEANS" not in cats or any(k in p["name"] for k in NON_BEAN):
            continue
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_connexcoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_connexcoffee.json に出力しました")


if __name__ == "__main__":
    main()
