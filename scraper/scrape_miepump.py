# -*- coding: utf-8 -*-
"""
scrape_miepump.py

miepump coffee shop(ミエポンプコーヒーショップ、京都府京都市左京区岩倉三宅町33-1 1F-C)の
カラーミーショップ(miepump.shop-pro.jp、EUC-JP)から焙煎豆の商品情報を取得する。

【対象】カテゴリ「コーヒー豆」(cbid=1599678、全10件前後)のうち、ストレート・ブレンドの200g豆(豆/粉は購入時に選択、
価格は共通)。除外: ギフトパッケージ(0円)・「100g包装袋×2」(包装オプション)。
商品名の末尾の「200g」を重量、「深煎り」等を焙煎度として抜き出し、名称から取り除く。
在庫は一覧の「SOLD OUT」表示で判定する(売り切れ商品は詳細ページが404になるため説明文は取得できない)。

【自家焙煎の根拠】販売ページ自体には「焙煎直後は…」「焙煎環境に関わるコスト増」の記述はあるが焙煎機の明記は無い。
第三者として Time Out Tokyo(2016年)が同店(当時 左京区浄土寺馬場町)を「手回しの焙煎機(1回500g)でオーナーが焙煎」と紹介。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "miepump coffee shop",
    "url": "http://miepump.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "京都府京都市左京区岩倉三宅町33-1 1F-C",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。robots.txtは/secure/と/cart/のみ禁止)",
    "source_note": "カラーミーショップのカテゴリ「コーヒー豆」(http://miepump.shop-pro.jp/?mode=cate&cbid=1599678&csid=0)と各商品ページを2026-10-21に確認。トップに「10月より価格改定」の告知(2026-10)。実店舗住所はトップの「実店舗のご案内」",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "http://miepump.shop-pro.jp"
CATEGORY_URL = BASE_URL + "/?mode=cate&cbid=1599678&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 1.6
EXCLUDE = ("ギフト", "包装袋")
ROAST_RE = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
WEIGHT_RE = re.compile(r"(\d+)\s*g")


def fetch(url):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    return resp


def scrape_list():
    resp = fetch(CATEGORY_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for t in soup.select("table.top_frame"):
        a = t.select_one("div.overflow_140px a[href*='pid=']")
        if not a:
            continue
        text = t.select_one("div.overflow_140px").get_text("\n", strip=True)
        pm = re.search(r"販売価格:([\d,]+)円", text)
        if not pm:
            continue
        items.append({
            "title": unicodedata.normalize("NFKC", a.get_text(strip=True)),
            "href": a["href"],
            "price": int(pm.group(1).replace(",", "")),
            "sold_out": "SOLD OUT" in text,
        })
    return items


def fetch_desc(href):
    time.sleep(INTERVAL)
    resp = fetch(f"{BASE_URL}/{href}")
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    t = soup.get_text("\n", strip=True)
    a, b = t.find("商品名："), t.find("豆の状態")
    if a < 0 or b < 0:
        return None
    lines = t[a:b].split("\n")[1:]
    out = [unicodedata.normalize("NFKC", l) for l in lines
           if "包装" not in l and not re.fullmatch(r"\[.*\]", unicodedata.normalize("NFKC", l))]
    return "\n".join(out).strip() or None


def build_record(it, desc):
    title = it["title"]
    roast_m = ROAST_RE.search(title)
    w_m = WEIGHT_RE.search(title)
    name = WEIGHT_RE.sub("", ROAST_RE.sub("", title))
    name = re.sub(r"\s+", " ", name).strip()
    parsed = parse_product(title)
    is_blend = "ブレンド" in name
    if is_blend:
        category, origin, origin_source = "ブレンド", None, None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        category = parsed["category"]
        origin = parsed["origin_country"]
        if origin == "グァテマラ":
            origin = "グアテマラ"
        origin_source = parsed["origin_source"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": None if is_blend else parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_m.group(1) if roast_m else None,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": int(w_m.group(1)) if w_m else None,
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/{it['href']}",
    }


def scrape_all_products():
    records = []
    for it in scrape_list():
        if any(k in it["title"] for k in EXCLUDE) or it["price"] <= 0:
            continue
        if not WEIGHT_RE.search(it["title"]):
            continue
        desc = None if it["sold_out"] else fetch_desc(it["href"])
        if it["sold_out"]:
            time.sleep(INTERVAL)
        records.append(build_record(it, desc))
    return records


def main():
    records = scrape_all_products()
    with open("data_miepump.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_miepump.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"])


if __name__ == "__main__":
    main()
