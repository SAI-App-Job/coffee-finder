# -*- coding: utf-8 -*-
"""
scrape_geniccoffee.py

GENIC COFFEE(ジェニックコーヒー、福岡県北九州市小倉北区竪町2-5-12)の公式EC(https://www.cafe-genic.com/、xaas3.jp系ASPカート)から
コーヒー豆(シングルオリジン・ブレンド)の商品情報を取得する。

【実店舗・自家焙煎の根拠】
公式サイト店舗案内 https://www.cafe-genic.com/aboutus.html に住所「〒803-0818 福岡県北九州市小倉北区竪町2-5-12」、
営業時間12:00～20:00・定休日火曜日(店舗2階は写真ギャラリー)。トップページに「ご注文をいただいてからその場で焙煎することで、
常に鮮度抜群のコーヒー豆をお客様に提供」「熱風式焙煎」。NAVITIMEにも同住所の店舗掲載あり。

【対象商品】
カテゴリ3「シングルオリジン」(18件)と カテゴリ4「ブレンド」(4件: ブレンド3 + シングルのタイ チェンライ)の計22商品の豆(全て100g)。
除外: ドリップパック(カテゴリ5)、生豆(カテゴリ6)、アーモンド(8)・ピスタチオ(9)等のナッツ類。
商品ページの情報は 商品名・価格・在庫・「焙煎度N」(シングルのみ。数値の尺度は店の説明なし)のみで、説明文・風味は無い。
価格は税込(商品ページ表記「販売価格」)。シングルの商品ページ上部の本文表記は税抜(例 1,500円=税込1,650円)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "GENIC COFFEE",
    "url": "https://www.cafe-genic.com/",
    "platform": "独自カート(xaas3.jp)",
    "address": "福岡県北九州市小倉北区竪町2-5-12",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。User-Agent: * で /default/error/ と /preview/ のみDisallow)",
    "source_note": "公式EC(https://www.cafe-genic.com/category/3 , /category/4 と各商品ページ)を2026-10-20に取得。店舗情報は /aboutus.html。商品ページに説明文はなく、更新日の記載も無いため更新の新旧は不明",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.cafe-genic.com"
CATEGORY_URLS = [f"{BASE_URL}/category/3", f"{BASE_URL}/category/4"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6

# 商品名の表記ゆれ(誤記含む)を補正した産地。キー=商品ページ上の国名表記
ORIGIN_FIX = {
    "インドネシア.マンデリン.ブルーバタック": "インドネシア",
    "エルサドバドル": "エルサルバドル",
    "パプァニューギニア": "パプアニューギニア",
}
ORIGIN_COUNTRIES = ["インドネシア", "ブラジル", "エルサドバドル", "パナマ", "エチオピア", "ドミニカ", "コロンビア", "ペルー",
                    "コスタリカ", "タンザニア", "コンゴ", "ミャンマー", "インド", "パプァニューギニア", "タイ"]
COUNTRY_CANON = {"エルサドバドル": "エルサルバドル", "パプァニューギニア": "パプアニューギニア", "コンゴ": "コンゴ民主共和国",
                 "ドミニカ": "ドミニカ共和国"}


def fetch(url: str) -> BeautifulSoup:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def clean_name(title: str) -> str:
    t = unicodedata.normalize("NFKC", title)
    t = t.replace("インドネシア.マンデリン.ブルーバタック", "インドネシア マンデリン ブルーバタック")
    t = re.sub(r"\s*100\s*g\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*100\s*g", "", t, flags=re.I)
    t = t.replace("エルサドバドル", "エルサルバドル").replace("パプァニューギニア", "パプアニューギニア")
    return re.sub(r"\s+", " ", t).strip()


def scrape_all_products() -> list:
    urls = []
    for cu in CATEGORY_URLS:
        soup = fetch(cu)
        time.sleep(REQUEST_INTERVAL)
        for a in soup.select('a[href*="/item/"]'):
            if a["href"] not in urls:
                urls.append(a["href"])
    records = []
    for url in urls:
        soup = fetch(url)
        time.sleep(REQUEST_INTERVAL)
        title = soup.select_one("div#itemDetail01 h2").get_text(strip=True)
        main = unicodedata.normalize("NFKC", soup.select_one("div.mainTxt").get_text(" ", strip=True))
        price_el = soup.select_one("li.sales_price strong")
        price = int(re.search(r"([\d,]+)円", price_el.get_text()).group(1).replace(",", ""))
        stock_txt = soup.select_one("li.stock1 p.data").get_text(strip=True)
        in_stock = "在庫あり" in stock_txt
        name = clean_name(title)
        blend_roast = None
        bm = re.search(r"[(（]\s*((?:浅|中浅|中|中深|深)煎り)\s*[)）]", name)
        if bm:   # ブレンド名末尾の「(浅煎り)」は焙煎度の目安(roast_hint)に回し、商品名から外す
            blend_roast = bm.group(1)
            name = re.sub(r"\s*[(（][^)）]*煎り[)）]", "", name).strip()
        is_blend = "ブレンド" in name
        parsed = parse_product(name)
        rm = re.search(r"焙煎度\s*(\d)", main)
        roast_hint = f"焙煎度{rm.group(1)}" if rm else blend_roast
        if is_blend:
            origin, origin_source, category = None, None, "ブレンド"
        else:
            category = "ストレート"
            first = unicodedata.normalize("NFKC", title).replace(".", " ").split()[0]
            first = first if first in ORIGIN_COUNTRIES else next((c for c in ORIGIN_COUNTRIES if title.startswith(c)), None)
            origin = COUNTRY_CANON.get(first, first)
            origin_source = "shop_attribute" if origin else None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": category,
            "origin_country": origin,
            "origin_source": origin_source,
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 100,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_geniccoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_geniccoffee.json に出力しました")


if __name__ == "__main__":
    main()
