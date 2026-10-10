# -*- coding: utf-8 -*-
"""
scrape_yamajicoffee.py

山路珈琲(YAMAJI COFFEE、長野県飯田市錦町1-7-2、公式 yamajicoffee.com)のオンラインショップ
(Jimdo: yamajicoffee.jimdofree.com)の商品情報を取得する。Jimdo(独自ショップ機能)。

【robots.txt】Disallow: /app/ と /j/、Crawl-Delay: 5(確認済み 2026-10)。/j/配下(商品詳細・規約)は
取得せず、商品情報が直接埋め込まれたショップのトップページ('/')1回の取得のみで全商品を取得する。
(住所は /特定商取引法に基づく表記/ で一度限り人力確認: 長野県飯田市錦町1-7-2)

【対象商品】トップに並ぶ15商品のうち、ブレンド3(山路・飯田・季節)とストレート/デカフェ7の計10点。
「×3か月」の定期配送商品と「深煎り３種セット」は除外。全商品150g、価格は税込・送料無料(送料込み)。
【product_url】商品ごとのページ(/j/配下)は取得対象外のためトップURL + '#商品名' で一意化。
【産地・焙煎度】商品説明の「産地：」「中深煎り」等から取得。記載が無いものは null。
【在庫】schema.org の availability(InStock)。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "山路珈琲",
    "url": "https://yamajicoffee.jimdofree.com/",
    "platform": "Jimdo(独自ショップ機能)",
    "address": "長野県飯田市錦町1-7-2",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(2026-10確認。/app/と/j/がDisallow・Crawl-Delay:5だが、商品が埋め込まれたトップページ'/'のみ取得)",
}

PAGE_URL = "https://yamajicoffee.jimdofree.com/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN = ["か月", "ヶ月", "ケ月", "セット", "定期"]
ORIGIN_HINTS = {"シダモ": "エチオピア"}  # 産地欄がシダモ(エチオピア南部の産地名)のみの商品用
ROAST_RE = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def fetch():
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def build_records(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    records = []
    for blk in soup.select("div.j-product"):
        h4 = blk.select_one("h4")
        if not h4:
            continue
        title = unicodedata.normalize("NFKC", h4.get_text(" ", strip=True))
        title = re.sub(r"\s+", " ", title).strip()
        if any(k in title for k in NON_BEAN):
            continue
        wm = re.search(r"(\d+)\s*g\s*$", title, re.I)
        weight = int(wm.group(1)) if wm else None
        name = re.sub(r"\s*\d+\s*g\s*$", "", title, flags=re.I).strip()
        desc_el = blk.select_one('[itemprop="description"]')
        desc = unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)) if desc_el else ""
        desc = re.sub(r"\s+", " ", desc)
        price_m = blk.select_one('[itemprop="price"]')
        price = int(price_m["content"]) if price_m and price_m.get("content") else None
        av = blk.select_one('link[itemprop="availability"], meta[itemprop="availability"]')
        in_stock = True
        if av:
            v = av.get("href") or av.get("content") or ""
            in_stock = "InStock" in v
        origin_m = re.search(r"産地[：:]\s*(\S+)", desc)
        origin_text = origin_m.group(1) if origin_m else ""
        rm = ROAST_RE.search(name) or ROAST_RE.search(desc)
        roast = rm.group(1) if rm else None

        parsed = parse_product(name)
        # 商品説明の精製方法表記(例:「ウォッシュド製法」)を、商品名からの推定より優先する
        parsed["processing_method"] = parse_product(desc)["processing_method"] or parsed["processing_method"]
        if "ウォッシュド製法" in desc:
            parsed["processing_method"] = "ウォッシュド"
        is_blend = "ブレンド" in name
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            c = detect_country_name(name) or detect_country_name(origin_text) or ORIGIN_HINTS.get(origin_text)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name" if detect_country_name(name) else "description"
            parsed = apply_category_hint_fallback(parsed, name)
        # 説明文のうち産地行・案内文(発送案内「※」)を除いた味の説明をflavor_notesに
        fl = [x for x in re.split(r"(?<=。)", desc)
              if x.strip() and "※" not in x and "産地:" not in x and "産地：" not in x and "焙煎日" not in x and "発送" not in x]
        flavor = "".join(fl).strip()[:300] or None
        records.append({
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
            "flavor_notes": flavor,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": PAGE_URL + "#" + quote(name),
        })
    return records


def scrape_all_products():
    return build_records(fetch())


def main():
    records = scrape_all_products()
    with open("data_yamajicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamajicoffee.json に出力しました")


if __name__ == "__main__":
    main()
