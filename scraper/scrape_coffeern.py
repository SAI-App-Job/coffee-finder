# -*- coding: utf-8 -*-
"""
scrape_coffeern.py

Coffee Roast Natural(コーヒーローストナチュラル、coffee-r-n.com、東京都大田区大森西3-12-28、
「生の珈琲豆をその場で焙煎いたします」の自家焙煎豆売所・1店舗)の商品情報を取得する。
WordPress。カートは無く、注文は電話またはInstagram DMのみ(配送ページ参照)。

【対象商品について】
実データ確認済み(2026-10時点): 「珈琲豆・メニュー表」(/coffee_list/)の静的な価格表
(産地見出し「アジア」「アフリカ」「太平洋」「カリブ海」「中南米」「南米」の下に
「銘柄(産地)」と「240g/1,650円」の行が並ぶ)を解析する。全て単一産地のストレートで
ブレンドの掲載は無い。サイトの最新のお知らせ(2026-09付)で価格(例: メキシコデカフェ
240g/2,050円)が更新されており、価格表は最新と判断した。
 - 「終売」「入荷予定なし」を含む銘柄(マンデリントバコ・クリスタルクィーン・
   アンデスマウンテン)は現在販売していないため除外。
 - 「欠品中」「現在在庫なし」(パラダイスプレミアム・クラシックモカ・マサイAA)は完売扱い。
重量・価格は各行の「N g/N円」(税込、1サイズのみ。多くは240g、ハワイコナ・
ブルーマウンテンのみ200g)。商品詳細ページは無いため、product_urlは価格表ページに
銘柄名のフラグメント(#銘柄名)を付けて一意にしている。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Coffee Roast Natural",
    "url": "https://coffee-r-n.com/",
    "platform": "WordPress(価格表のみ・電話/DM注文)",
    "address": "東京都大田区大森西3-12-28",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

LIST_URL = "https://coffee-r-n.com/coffee_list/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REGION_HEADINGS = {"アジア", "アフリカ", "太平洋", "カリブ海", "中南米", "南米"}
PRICE_LINE = re.compile(r"^(\d+)\s*g\s*/\s*([\d,]+)\s*円")
DISCONTINUED = ("終売", "入荷予定なし")
OUT_OF_STOCK = ("欠品", "在庫なし")
ROAST_HINT = "注文ごとに店内で焙煎(生豆をその場で焙煎)"
# 「(括弧内)」が国名でないもの・国名が名前に出ないものの補正
ORIGIN_OVERRIDES = {
    "ニューギニア": "パプアニューギニア",
    "ハワイ": "アメリカ(ハワイ)",
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_list(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    entry = soup.select_one("div.entry-content, .post_content, article, main") or soup
    lines = [ln.strip() for ln in entry.get_text("\n", strip=True).split("\n") if ln.strip()]
    items = []
    i = 0
    while i < len(lines) - 1:
        m = PRICE_LINE.match(unicodedata.normalize("NFKC", lines[i + 1]))
        if m and lines[i] not in REGION_HEADINGS:
            items.append({
                "name_line": lines[i],
                "price_line": lines[i + 1],
                "weight_g": int(m.group(1)),
                "price": int(m.group(2).replace(",", "")),
            })
            i += 2
        else:
            i += 1
    return items


def build_record(item: dict) -> dict | None:
    line = item["name_line"]
    both = line + " " + item["price_line"]
    if any(k in both for k in DISCONTINUED):
        return None
    out = any(k in both for k in OUT_OF_STOCK)
    name = re.sub(r"(現在在庫なし|欠品中.*|終売.*)$", "", line).strip()
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name))
    parsed = parse_product(name)
    parsed["category"] = "ストレート"
    parsed = apply_category_hint_fallback(parsed, name)
    # 括弧内の産地表記から国を補う(例: カロシトラジャ(インドネシア))
    pm = re.search(r"[（(]([^）)]+)[）)]", name)
    if pm and not parsed["origin_country"]:
        inner = pm.group(1)
        country = next((c for k, c in ORIGIN_OVERRIDES.items() if k in inner), None) or detect_country_name(inner)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "country_name"
    if not parsed["origin_country"]:
        country = next((c for k, c in ORIGIN_OVERRIDES.items() if k in name), None)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "raw_name"
    if "ハワイ" in name:
        parsed["origin_country"] = "アメリカ(ハワイ)"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": ROAST_HINT,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{LIST_URL}#{quote(name)}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list(fetch(LIST_URL)):
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeern.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeern.json に出力しました")


if __name__ == "__main__":
    main()
