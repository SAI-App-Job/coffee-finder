# -*- coding: utf-8 -*-
"""
scrape_kanazawayacoffee.py

金澤屋珈琲店(krf.co.jp、石川県金沢市丸の内5-26、金沢城公園黒門口横。キャラバンサライの
コンセプトショップ、運営はキャラバンサライ株式会社)の商品情報を取得する。
ショップサーブ形式(/SHOP/<商品コード>.html)。キャラバンサライ(www.caravanserai.co.jp)とは
別カート(別ドメイン・別商品コード)。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【robots.txtについて】
実データ確認済み(2026-10-12): robots.txt自体が存在しない(404)ため、Disallow指定は無く
実質許可。識別可能な独自User-Agentを使用する。

【キャラバンサライとの重複の扱いについて】
実データ確認済み(2026-10-12): 豆カテゴリ(ブレンド11・シングル14・高級4〈シングルと重複〉・
デカフェ3)のうち、キャラバンサライ(scrape_caravanserai.py)と同名・同銘柄の商品
(秋ブレンド、兼六坂、百万石、かなざわ物語、城下町、加賀美人、カフェプリモ、カフェ・イタリアン、
全シングルオリジン、デカフェ3種)は、同一会社の同一商品を別カートで200g規格(キャラバンサライは
主に100g)で販売しているものであり、統合時に二重計上になるため収録しない。
金澤屋珈琲店のカートにしか無い「近江町ブレンド」「極みブレンド(本店限定品)」「利家ブレンド
(本店限定品)」の3件のみを収録する。
価格は200g・税込表示(商品一覧の「(税込)」)。500g/1kgは同一ページ内のまとめ買いオプション。

【商品情報の取得方法について】
商品名・価格・在庫は商品一覧(自家焙煎ブレンドコーヒー豆、SHOP/1175349/25386)の各商品
カードから、説明文は各商品ページの<meta name="description">から取得する。焙煎度は
商品ページ本文に明記された商品(近江町=「深煎り豆をベース」、極み=「極上の深煎り」)のみ指定し、
明記が無い利家ブレンドはnullとする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

SHOP_INFO = {
    "name": "金澤屋珈琲店",
    "url": "https://www.krf.co.jp/",
    "platform": "ショップサーブ",
    "address": "石川県金沢市丸の内5-26",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(2026-10-12確認。robots.txt自体が存在しない(404)ためDisallow指定は無い)",
}

BASE_URL = "https://www.krf.co.jp"
LIST_URL = f"{BASE_URL}/SHOP/1175349/25386/list.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# このストア固有の商品: 商品コード -> (商品名, 焙煎度)
TARGETS = {
    "K013": ("近江町ブレンド", "深煎り"),
    "K051": ("極みブレンド", "深煎り"),
    "K052": ("利家ブレンド", None),
}
WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[）)]")
SOLD_OUT_PATTERN = re.compile(r"在庫切れ|売り切れ|品切れ|SOLD\s*OUT|完売")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def scrape_all_products() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    form = soup.select_one("#itemList")
    records = []
    for sec in (form.select("section") if form else []):
        a = sec.select_one("h2 a")
        price_el = sec.select_one(".selling_price")
        if not a or not price_el:
            continue
        m = re.search(r"/SHOP/([A-Za-z0-9\-]+)\.html", a.get("href", ""))
        if not m or m.group(1) not in TARGETS:
            continue
        code = m.group(1)
        name, roast = TARGETS[code]
        title = a.get_text(strip=True)
        weight_m = WEIGHT_PATTERN.search(title)
        price = int(re.sub(r"[^\d]", "", price_el.get_text()) or 0) or None
        stock_el = sec.select_one(".sps-itemList-stockDisp")
        sold_out = bool(SOLD_OUT_PATTERN.search(stock_el.get_text(" ", strip=True))) if stock_el else False
        html_text = fetch(f"{BASE_URL}/SHOP/{code}.html")
        desc_m = re.search(r'<meta name="description" content="([^"]*)"', html_text)
        desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "ブレンド",
            "origin_country": None,
            "origin_source": None,
            "designated_brand": None,
            "processing_method": None,
            "grade": None,
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": [],
            "blend_components": [],
            "price": price,
            "weight_g": int(weight_m.group(1)) if weight_m else None,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/SHOP/{code}.html",
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_kanazawayacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kanazawayacoffee.json に出力しました")


if __name__ == "__main__":
    main()
