# -*- coding: utf-8 -*-
"""
scrape_minaminocoffeesen.py

南乃珈琲船(みなみのコーヒーせん、東京都世田谷区北沢3-17-3 ベルエアしもきた103、下北沢の自家焙煎(直火式)珈琲豆店)の
ネットショップ(shop.minamino-coffee-sen.com、カラーミーショップ・EUC-JP)から商品情報を取得する。
このドメインは http のみで応答する(https は接続不可)。

【対象商品について】
焙煎度別カテゴリ(フレンチロースト=深煎り7件・シティロースト=中深煎り4件・ハイロースト=浅煎り2件、計13件)が
対象。いずれも「1袋(200g)」で、豆/粉の選択でも価格は同じ。一覧に商品名・税込価格・説明・SOLD OUT表示が出ているため、
一覧から取得し、重量だけ各商品の詳細ページで確認する。
除外: アイスコーヒー(1リットルの液体3件)、ギフトセット(詰め合わせ3件)。
重量は詳細ページの「袋(200g)」表記から取得する(SOLD OUT のマンデリンフレンチは詳細ページに数量欄が無く重量表記が無いため null)。
産地は商品名で判明するもの(ブラジル・コロンビア・ガテマラ・パプアニューギニア・マンデリン・モカ=エチオピア・
タンザニア)のみ。「北沢ブレンド」「南乃珈琲船ブレンド」はブレンド。

robots.txt(http://shop.minamino-coffee-sen.com/robots.txt): User-agent:* で /secure/ と /cart/ のみ Disallow(2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "南乃珈琲船",
    "url": "http://shop.minamino-coffee-sen.com/",
    "platform": "カラーミーショップ",
    "address": "東京都世田谷区北沢3-17-3 ベルエアしもきた103",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/ と /cart/ のみ禁止)",
    "source_note": "ネットショップの焙煎度別カテゴリ3つ(フレンチ・シティ・ハイロースト、計13件)と各商品詳細を2026-10-25に確認。公式 http://www.minamino-coffee-sen.com/ に『下北沢で自家焙煎(直火式)珈琲豆を販売する小さなお店』『2015年6月6日開店』、ショップのフッターに『自家焙煎珈琲工房 南乃珈琲船』と住所・電話。商品に日付表記は無く更新時期は不明(SOLD OUT表示は運用中)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "http://shop.minamino-coffee-sen.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
# (カテゴリID, 焙煎度)
CATEGORIES = [("1996893", "深煎り"), ("1996894", "中深煎り"), ("1996895", "浅煎り")]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    time.sleep(REQUEST_INTERVAL)
    return resp.text


def fetch_listing() -> list[dict]:
    items, seen = [], set()
    for cbid, roast in CATEGORIES:
        html = fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0")
        for b in re.split(r'<div style="margin-top: 10px;float:left; width:200px;"', html)[1:]:
            m = re.search(r'<a href="\?pid=(\d+)">([^<]+)</a>', b)
            p = re.search(r"([\d,]+)円", b)
            if not m or not p or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            d = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.split("</a>", 2)[-1]))
            d = re.split(r"\d+〜\d+件", d)[0]
            d = re.sub(r"[\d,]+円\(税込\)|SOLD OUT", "", d).strip()
            items.append({
                "pid": m.group(1),
                "name": m.group(2).strip(),
                "price": int(p.group(1).replace(",", "")),
                "roast": roast,
                "desc": d or None,
                "sold_out": "SOLD OUT" in b,
            })
    return items


def fetch_weight(pid: str):
    html = fetch(f"{BASE_URL}/?pid={pid}")
    m = re.search(r"袋[（(]\s*(\d+)\s*[gｇ]\s*[）)]", html)
    return int(m.group(1)) if m else None


def build_record(it: dict) -> dict:
    name = it["name"]
    parsed = parse_product(name)
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and re.search(r"イルガ[シチ]ェフェ", name):
            # イルガチェフェ(イルガシェフェ)はエチオピアの産地名
            parsed["origin_country"], parsed["origin_source"] = "エチオピア", "region_name"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": it["roast"],
        "flavor_notes": it["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "一時的に品切れ" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/?pid={it['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in fetch_listing():
        it["weight"] = fetch_weight(it["pid"])
        records.append(build_record(it))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_minaminocoffeesen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_minaminocoffeesen.json に出力しました")


if __name__ == "__main__":
    main()
