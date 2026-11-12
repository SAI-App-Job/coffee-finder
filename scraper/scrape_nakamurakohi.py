# -*- coding: utf-8 -*-
"""
scrape_nakamurakohi.py

備長炭焙煎 中村珈琲(宮崎県北諸県郡三股町、https://www.nakamura-coffee.com/)の商品情報を取得する。
「そのまんま百貨店」(sonomanma.co.jp)系のCGIカート(shopping/main.cgi、Shift_JIS)。

【店舗の確認(2026-11-03)】
トップに「備長炭焙煎 中村珈琲は…珈琲豆焙煎工房です。生豆を丁寧にハンドピックし、国産の備長炭のみで
焙煎しております」「宮崎県北諸県郡三股町 大字宮村2874-2 営業時間12:00〜19:00 定休日 月曜日・火曜日」
(焙煎工房兼店舗)。特商法ページ(mode=celaw)の所在地も同じ。単独1店舗。
(同名の兵庫県「NAKAMURA coffee」(scrape_nakamuracoffee.py)、三重県の別店舗とは別の店。)

【対象商品について】
カテゴリ「ブレンド珈琲」9件・「ストレート珈琲」12件の豆を対象にする。いずれも200g(豆のまま/細挽き/
中挽き/粗挽きを選択でき、豆のままの価格は同額)の単一重量で、重量違いの重複はない。
除外: カテゴリ「アイスコーヒー」の水出しアイスコーヒーパック、ギフトセット、コーヒー器具。
在庫は一覧の売り切れ画像(soldout.gif)の有無で判定する。
焙煎度はストレートの説明文に明記されたもののみ採用(ブレンドの説明は「深煎りの豆をベースに」等
ベース豆の記述のため、焙煎度は採用しない)。
robots.txtは404(制限なし)。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "中村珈琲",
    "url": "https://www.nakamura-coffee.com/",
    "platform": "そのまんま百貨店(独自CGIカート)",
    "address": "宮崎県北諸県郡三股町大字宮村2874-2",
    "prefecture": "宮崎県",
    "robots_txt_status": "制限なし(2026-11-03確認。robots.txtは404)",
    "source_note": "公式ショップ(https://www.nakamura-coffee.com/shopping/main.cgi)のカテゴリ「ブレンド珈琲」「ストレート珈琲」の一覧を2026-11-03に確認。ブログ最新記事は2026-10-28",
    "last_verified_at": "2026-11-03",
}

BASE = "https://www.nakamura-coffee.com/shopping/main.cgi"
CATEGORIES = [
    ("ブレンド", "%83u%83%8C%83%93%83h%E0%DB%E0%E8"),
    ("ストレート", "%83X%83g%83%8C%81%5B%83g%E0%DB%E0%E8"),
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2

ORIGIN_MAP = {
    "ブラジル": "ブラジル",
    "グァテマラ": "グアテマラ",
    "タンザニア": "タンザニア",
    "インドネシア": "インドネシア",
    "コロンビア": "コロンビア",
    "エチオピア": "エチオピア",
}
ROAST_RE = re.compile(r"(中深|中浅|極深|浅|中|深)煎り")
BLOCK_SPLIT = re.compile(r'(?=<table width="100%" border="0" cellspacing="0" cellpadding="4">)')
NAME_RE = re.compile(r'mode=details&sid=1&gid=(\w+)"><u>([^<]*)')
PRICE_RE = re.compile(r"価格：.*?<b>\s*([\d,]+)", re.S)
DESC_RE = re.compile(r'<font size="2" color="#666666">\s*([^<]{5,}?)</font></td>\s*<td width="25%" align="left"', re.S)


def fetch(category_param: str) -> str:
    url = f"{BASE}?mode=cart&sid=1&g1={category_param}&g2="
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content.decode("cp932", errors="replace")


def build_record(kind: str, gid: str, raw: str, price: int, sold_out: bool, desc: str) -> dict | None:
    raw = unicodedata.normalize("NFKC", raw)
    wm = re.search(r"[(（]\s*(\d+)\s*[gｇ]\s*[)）]", raw)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"\s*[(（]\s*\d+\s*[gｇ]\s*[)）]", "", raw)
    name = re.sub(r"\s+", " ", name).strip()
    parsed = parse_product(name)
    roast = None
    if kind == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        first = name.split(" ")[0]
        parsed["origin_country"] = ORIGIN_MAP.get(first, parsed["origin_country"])
        parsed["origin_source"] = "raw_name"
        rm = ROAST_RE.search(desc)
        roast = rm.group(0) if rm else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE}?mode=details&sid=1&gid={gid}",
    }


def scrape_all_products() -> list:
    records = []
    for idx, (kind, param) in enumerate(CATEGORIES):
        if idx:
            time.sleep(REQUEST_INTERVAL)
        html_text = fetch(param)
        for block in BLOCK_SPLIT.split(html_text):
            m = NAME_RE.search(block)
            pm = PRICE_RE.search(block)
            if not (m and pm):
                continue
            dm = DESC_RE.search(block)
            desc = re.sub(r"\s+", " ", dm.group(1)).strip() if dm else ""
            rec = build_record(kind, m.group(1), m.group(2), int(pm.group(1).replace(",", "")),
                               "soldout.gif" in block, desc)
            if rec:
                records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_nakamurakohi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nakamurakohi.json に出力しました")


if __name__ == "__main__":
    main()
