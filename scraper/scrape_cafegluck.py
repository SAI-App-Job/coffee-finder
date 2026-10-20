# -*- coding: utf-8 -*-
"""
scrape_cafegluck.py

自家焙煎珈琲カフェ・グリュック(Cafe Gluck、福岡県久留米市日吉町18-48)の公式EC(https://www.cafe-gluck.com/、ショップサーブ)から
コーヒー豆(ストレート・ブレンド)の商品情報を取得する。

【実店舗・自家焙煎の根拠】
公式サイト https://www.cafe-gluck.com/ のタイトル「自家焙煎珈琲専門店カフェ・グリュック 福岡県久留米市日吉町」、
各商品説明に「カフェ・バッハグループで共同購入した…コーヒー豆を使用し、焙煎前後でハンドピック…焙煎をしています」、
「お店のご案内」https://www.cafe-gluck.com/hpgen/HPB/entries/1.html に「830-0017 福岡県 久留米市 日吉町 18-48(グリーンリッチホテル久留米隣)」、
営業時間11:00-17:00・定休日毎週水曜日・第四木曜日、サイトに「店内メニュー」「お持ち帰りメニュー」。特商法表示の許認可に
「SCAJ認定アドバンスドコーヒーマイスター」。第三者掲載(ウォーカープラス等)でも久留米市日吉町18-48の自家焙煎店として紹介。

【対象商品】
カテゴリ「ストレート」(101386、10件)と「ブレンド」(95179)の豆(全て100g、豆のまま/挽き分け同価格)。
除外: ブレンド・セット(O-1)、ドリップバッグ(D-1)、水出しコーヒー(W-1)、ギフト、コーヒー器具。
【価格改定の予告】
ショップからのお知らせ(2026.09.17)に「11月01日(日)より商品の販売価格を改定」とあるため、取得時点(2026-10-20)の価格を採用。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "Cafe Gluck",
    "url": "https://www.cafe-gluck.com/",
    "platform": "ショップサーブ",
    "address": "福岡県久留米市日吉町18-48",
    "prefecture": "福岡県",
    "robots_txt_status": "robots.txtなし(404、2026-10-20確認。制限の記載なし)",
    "source_note": "公式EC(https://www.cafe-gluck.com/SHOP/101386/list.html ほか)を2026-10-20に取得。ショップからのお知らせの最新は2026.10.02。2026-11-01に販売価格改定の予告あり(取得は改定前の価格)",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.cafe-gluck.com"
LIST_URLS = [(f"{BASE_URL}/SHOP/101386/list.html", "ストレート"), (f"{BASE_URL}/SHOP/95179/list.html", "ブレンド")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6
EXCLUDE_WORDS = ["セット", "ドリップバッグ", "水出し", "ギフト"]
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)\s*$")
BOILER = "それぞれのコーヒー豆の特徴を活かした焙煎をしています。"


def fetch(url: str) -> BeautifulSoup:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup


def list_items(list_url: str):
    soup = fetch(list_url)
    items, seen = [], set()
    for a in soup.select('a[href^="/SHOP/"]'):
        href = a["href"]
        txt = a.get_text(strip=True)
        if "list" in href or "mailmag" in href or not txt:
            continue
        if href in seen:
            continue
        seen.add(href)
        items.append((BASE_URL + href, txt))
    return items


def detail(url: str) -> dict:
    soup = fetch(url)
    text = soup.get_text("\n", strip=True)
    pm = re.search(r"¥([\d,]+)", text)
    price = int(pm.group(1).replace(",", "")) if pm else None
    sm = re.search(r"在庫:\n(\S+)", text)
    stock_txt = sm.group(1) if sm else ""
    i = text.find(BOILER)
    desc = None
    blend = []
    if i >= 0:
        j = text.find("メニュー\n店内メニュー", i)
        body = text[i + len(BOILER):j if j > 0 else None]
        desc = re.sub(r"\s+", " ", body).strip() or None
        bm = re.search(r"は、([^。]*?)をブレンドした", body)
        if bm:
            blend = [c.strip() for c in bm.group(1).split("、") if c.strip()]
        if desc and len(desc) > 300:
            desc = desc[:300].rstrip() + "…"
    return {"price": price, "in_stock": "在庫あり" in stock_txt, "desc": desc, "blend": blend}


def scrape_all_products() -> list:
    records = []
    for list_url, cname in LIST_URLS:
        for url, title in list_items(list_url):
            time.sleep(REQUEST_INTERVAL)
            if any(w in title for w in EXCLUDE_WORDS):
                continue
            t = unicodedata.normalize("NFKC", title)
            rm = ROAST_PATTERN.search(t)
            roast = rm.group(1) if rm else None
            name = re.sub(r"\s*\(\s*\d+\s*g\s*\)", " ", t)
            name = ROAST_PATTERN.sub("", name)
            name = re.sub(r"\s+", " ", name).strip()
            d = detail(url)
            time.sleep(REQUEST_INTERVAL)
            parsed = parse_product(name.replace("インディア", "インド"))   # 商品名の「インディア」はインド産
            parsed["raw_name"] = name
            if cname == "ブレンド":
                parsed["category"] = "ブレンド"
                parsed["origin_country"] = None
                parsed["origin_source"] = None
            else:
                parsed = apply_category_hint_fallback(parsed, name)
                parsed["category"] = "ストレート"
            components = [{"origin_country": (parse_product(c.replace("インディア", "インド"))["origin_country"] or c),
                           "percentage": None} for c in d["blend"]]
            records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": name,
                "category": parsed["category"],
                "origin_country": parsed["origin_country"],
                "origin_source": parsed["origin_source"],
                "designated_brand": parsed["designated_brand"],
                "processing_method": parsed["processing_method"],
                "grade": parsed["grade"],
                "roast_level": parsed["roast_level"],
                "roast_hint": roast,
                "flavor_notes": d["desc"],
                "farm_note": None,
                "post_processing_tags": parsed["post_processing_tags"],
                "blend_components": components,
                "price": d["price"],
                "weight_g": 100,
                "stock_status": "販売中" if d["in_stock"] else "完売",
                "out_of_stock": not d["in_stock"],
                "product_url": url,
            })
    return records


def main():
    records = scrape_all_products()
    with open("data_cafegluck.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafegluck.json に出力しました")


if __name__ == "__main__":
    main()
