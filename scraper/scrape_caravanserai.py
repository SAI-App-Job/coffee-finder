# -*- coding: utf-8 -*-
"""
scrape_caravanserai.py

コーヒーのキャラバンサライ(caravanserai.co.jp、石川県金沢市保古3-47〈本店〉、
金沢市内を中心に全8店)の商品情報を取得する。ショップサーブ形式
(/SHOP/<商品コード>.html)の自社オンラインショップ。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【robots.txtについて】
実データ確認済み(2026-10-12): robots.txt自体が存在しない(404)ため、Disallow指定は無く
実質許可。識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(2026-10-12時点): 「コーヒー豆」配下の次の3カテゴリを巡回する。
  - 自家焙煎ブレンドコーヒー豆   (SHOP/92595)  10件
  - 自家焙煎シングルオリジンコーヒー豆 (SHOP/92232) 14件
  - 自家焙煎カフェインレスコーヒー豆(デカフェ) (SHOP/93257) 豆3件
    (同カテゴリ内のドリップバッグ・アイスコーヒー・カフェオレベースは除外)
ドリップバッグ・ギフト・セット・金箔入インスタント・菓子・器具は対象外。
各商品は100g(一部200g)の1種類のみが商品登録されており、500g/1kgは「まとめ買い」
(同一商品ページ内の割引オプション)のため、商品ページに表示される基本重量・価格を採用する。
価格は税込表示(商品一覧の「(税込)」)をそのまま採用する。

【商品情報の取得方法について】
商品名・価格・在庫は商品一覧の各商品カード(h2、.selling_price、在庫表示欄)から、
焙煎度は商品ページ本文に埋め込まれた見出し「<名称> 100g｜中煎り」から、説明文は
商品ページの<meta name="description">から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "キャラバンサライ",
    "url": "https://www.caravanserai.co.jp/",
    "platform": "ショップサーブ",
    "address": "石川県金沢市保古3-47(本店)",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(2026-10-12確認。robots.txt自体が存在しない(404)ためDisallow指定は無い)",
}

BASE_URL = "https://www.caravanserai.co.jp"
CATEGORIES = ["92595", "92232", "93257"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_KEYWORDS = ["ドリップバッグ", "アイスコーヒー", "カフェオレ", "ギフト", "セット", "インスタント", "羊羹", "ゼリー"]
WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[）)]")
ROAST_PATTERN = re.compile(r"[|｜][^<>\n]{0,12}?(浅煎り|中浅煎り|中煎り|中深煎り|深煎り|極深煎り)")
SOLD_OUT_PATTERN = re.compile(r"在庫切れ|売り切れ|品切れ|SOLD\s*OUT|完売")

# 商品名に国名が無いか、coffee_parserの辞書で検出できない銘柄の産地を明示する
# (いずれも商品ページの説明文で確認済み)
ORIGIN_OVERRIDES = {
    "ST010": "ジャマイカ",   # ブルーマウンテンNo.1(ジャマイカ東部ブルーマウンテン地域)
    "ST032": "コロンビア",   # ウィラ・マリア農園(ウィラ県)
    "ST040": "エチオピア",   # モカ・アビシニア(ゲディオ地区コンガ村)
    "ST011": "エチオピア",   # モカ・イリガチェフ
    "ST018": "ブラジル",     # センテニアル・ブルボン(サンタアリーナ農園、ブラジル)
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_category_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat in CATEGORIES:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/SHOP/{cat}/list.html"), "html.parser")
        form = soup.select_one("#itemList")
        if not form:
            continue
        for sec in form.select("section"):
            a = sec.select_one("h2 a")
            price_el = sec.select_one(".selling_price")
            if not a or not price_el:
                continue
            title = re.sub(r"\s+", " ", a.get_text(strip=True)).strip()
            m = re.search(r"/SHOP/([A-Za-z0-9\-]+)\.html", a.get("href", ""))
            if not m:
                continue
            code = m.group(1)
            if any(kw in title for kw in EXCLUDE_KEYWORDS):
                continue
            price = int(re.sub(r"[^\d]", "", price_el.get_text()) or 0) or None
            stock_el = sec.select_one(".sps-itemList-stockDisp")
            stock_text = stock_el.get_text(" ", strip=True) if stock_el else ""
            if code not in items:
                items[code] = {"code": code, "title": title, "price": price, "stock_text": stock_text, "cat": cat}
    return list(items.values())


def fetch_detail(code: str) -> dict:
    html_text = fetch(f"{BASE_URL}/SHOP/{code}.html")
    roast_m = ROAST_PATTERN.search(html_text)
    desc_m = re.search(r'<meta name="description" content="([^"]*)"', html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    return {"roast": roast_m.group(1) if roast_m else None, "desc": desc, "html": html_text}


def build_record(item: dict) -> dict:
    code = item["code"]
    detail = fetch_detail(code)
    title = item["title"]
    name = re.sub(r"\s+", " ", WEIGHT_PATTERN.sub("", title)).replace("【特別販売】", "").strip()
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    parsed = parse_product(name)
    if item["cat"] == "92595":
        parsed["category"] = "ブレンド"  # ブレンドカテゴリ(カフェ・モーニング等は名称に「ブレンド」が無い)
    elif item["cat"] == "93257" and "カフェインレスブレンド" not in name:
        parsed["category"] = "ストレート"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if code in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[code]
            parsed["origin_source"] = "raw_name"

    sold_out = bool(SOLD_OUT_PATTERN.search(item["stock_text"]))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": detail["roast"] or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": detail["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/SHOP/{code}.html",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_category_items():
        try:
            records.append(build_record(item))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['code']} ({e})")
    return records


def main():
    records = scrape_all_products()
    with open("data_caravanserai.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_caravanserai.json に出力しました")


if __name__ == "__main__":
    main()
