# -*- coding: utf-8 -*-
"""
scrape_nemunoki.py

自家焙煎珈琲 合歓の木(三重県津市羽所町356 エイトビル1階、公式 https://www.nemunokicafe.jp/、1976年創業)の
コーヒー豆通販ページの商品情報を取得する。独自の静的HTML+買物カゴCGI(UTF-8)。

【対象商品】
- ストレート: shop/<slug>.html の商品別ページ16件(ブルーマウンテン〜深煎りコロンビア)
- ブレンド: shop/blend-coffee2.html に全ブレンドが載り、<a name="blend-xxx"> のアンカー単位で商品化
  (商品コード code=1008〜)。product_url は ページURL#blend-xxx。
- 除外: お試しセット(set-a/set-b)、アイスコーヒー(Ice Liquid Coffee 1Lのリキッド)。
- 重量は全て 100g 単価(税込)。「コーヒー豆入荷困難につき、只今販売を中止しております。」が
  HTMLコメントの外にある商品は品切れ扱い(単価はコメントアウトされて残っているので価格は取得する)。
- 焙煎度は公式に記載がなく、商品名に「深煎り」「イタリアンロースト」等がある場合のみ採用。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲 合歓の木",
    "url": "https://www.nemunokicafe.jp/",
    "platform": "独自の静的HTML+買物カゴCGI",
    "address": "三重県津市羽所町356 エイトビル1階",
    "prefecture": "三重県",
    "robots_txt_status": "未確認(独自サイト、/shop/ は取得可)",
}

BASE = "https://www.nemunokicafe.jp/shop/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

STRAIGHT_PAGES = [
    "blue-mountain", "mokha-mattari", "jamaica", "tanzania-kilimanjaro", "hawai-kona",
    "high-mountain", "crystal-mountain", "brazilsantos", "columbia-medellin", "guatemala",
    "b-alegre", "sumateramanderin", "javarobusta", "toragear", "brazilsantos2", "columbia-medellin2",
]
# 産地行(■産地:)から国名への補完
ORIGIN_FROM_LINE = [("ブラジル", "ブラジル"), ("ジャマイカ", "ジャマイカ"), ("イエメン", "イエメン"),
                    ("タンザニア", "タンザニア"), ("ハワイ", "アメリカ"), ("キューバ", "キューバ"),
                    ("コロンビア", "コロンビア"), ("グァテマラ", "グアテマラ"), ("インドネシア", "インドネシア")]

PRICE_RE = re.compile(r"単価\s*:\s*([\d,]+)円")
SOLD_OUT_RE = re.compile(r"只今販売を中止")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def is_sold_out(chunk: str) -> bool:
    visible = re.sub(r"<!--.*?-->", "", chunk, flags=re.S)
    return bool(SOLD_OUT_RE.search(visible))


def roast_from_name(name: str):
    if "深煎り" in name:
        return "深煎り"
    if "イタリアン" in name:
        return "深煎り"
    return None


def make_record(name, price, url, is_blend, desc, origin_hint, sold_out):
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if origin_hint:
            parsed["origin_country"] = origin_hint
            parsed["origin_source"] = "raw_name" if origin_hint in name else "description"
        else:
            c = detect_country_name(name)
            if c and not parsed["origin_country"]:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_from_name(name),
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_straight(slug):
    url = BASE + slug + ".html"
    t = get(url)
    m = re.search(r'<h2><font color="#aa0000">■\s*([^<]*)</font>', t)
    if not m:
        return None
    name = m.group(1).strip()
    pm = PRICE_RE.search(t)
    price = int(pm.group(1).replace(",", "")) if pm else None
    line = re.search(r"■産地：([^<]*)", t)
    origin = None
    if line:
        for key, country in ORIGIN_FROM_LINE:
            if key in line.group(1):
                origin = country
                break
    h3 = re.search(r"<h3>([^<]*)</h3>", t)
    desc = h3.group(1).strip() if h3 and "こだわりの直火式" not in h3.group(1) else None
    return make_record(name, price, url, False, desc, origin, is_sold_out(t))


def scrape_blends():
    page = BASE + "blend-coffee2.html"
    t = get(page)
    parts = re.split(r'<a name="(blend-[a-z0-9]+)">', t)
    recs = []
    for i in range(1, len(parts), 2):
        anchor, chunk = parts[i], parts[i + 1]
        nm = re.search(r'<div class="h3red">■\s*合歓の木\s*([^<]*)</div>', chunk)
        if not nm:
            nm = re.search(r'<div class="h3red">■\s*([^<]*)</div>', chunk)
        if not nm:
            continue
        name = nm.group(1).strip()
        pm = PRICE_RE.search(chunk)
        price = int(pm.group(1).replace(",", "")) if pm else None
        dm = re.search(r'name="back"[^>]*/>\s*(.*?)<!--買物カゴ-->', chunk, flags=re.S)
        desc = None
        if dm:
            desc = re.sub(r"\s+", "", re.sub(r"<br\s*/?>", "", dm.group(1))) or None
        recs.append(make_record(name, price, page + "#" + anchor, True, desc, None, is_sold_out(chunk)))
    return recs


def scrape_all_products():
    records = []
    for slug in STRAIGHT_PAGES:
        r = scrape_straight(slug)
        if r:
            records.append(r)
        time.sleep(0.5)
    records.extend(scrape_blends())
    return records


def main():
    records = scrape_all_products()
    with open("data_nemunoki.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nemunoki.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], r["product_url"][-30:])


if __name__ == "__main__":
    main()
