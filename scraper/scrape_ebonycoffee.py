# -*- coding: utf-8 -*-
"""
scrape_ebonycoffee.py

EBONY COFFEE(エボニーコーヒー、東京都世田谷区奥沢6-28-4、2011年開業のスペシャルティコーヒーのロースタリー)の
ショップ(ebonycoffee.tokyo、旧 cloudnine.shop-pro.jp からリダイレクト、カラーミーショップ・EUC-JP)から商品情報を取得する。

【対象商品について】
商品カテゴリ「ブレンド」(5件)・「シングルオリジン」(10件)・「デカフェ」(1件)の計16件が対象で、すべて200g入り。
同じ銘柄でも焙煎度違い(シティ/フレンチ)は別商品として並ぶので、そのまま別商品として扱う(商品名に焙煎度が入る)。
除外: お試しセット(初回限定の50g×4種・100g×3種のセット3件)、ギフト、業務用コーヒー。
価格は一覧の「2,150円(税込2,322円)」の税込価格(2,322円)を採用する。SOLD OUTの「マイルストーン・ブレンド」は
一覧に価格が出ないので詳細ページの販売価格(sales)を使う。このブレンドは15周年記念の『6月末までの限定販売(予定)…早期終売』と
詳細ページにあるため stock_status は「終売」とする。
焙煎度は商品名の（シティ・ロースト）等(parse_productで判定)。

robots.txt(https://ebonycoffee.tokyo/robots.txt): User-agent:* で /secure/ と /cart/ のみ Disallow(2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "EBONY COFFEE",
    "url": "https://ebonycoffee.tokyo/",
    "platform": "カラーミーショップ",
    "address": "東京都世田谷区奥沢6-28-4",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/ と /cart/ のみ禁止)",
    "source_note": "ショップのカテゴリ(ブレンド・シングルオリジン・デカフェ、計16件)を2026-10-25に確認。住所は特定商取引法に基づく表記ページ・coffeegift.jp。自家焙煎の根拠は公式 About Us の『世界ハイエンドのスペシャルティコーヒーのみを扱うロースタリーです(2011年開業)』。新入荷(ホンジュラス ピカーチョ等)は2026年8月以降の商品",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://ebonycoffee.tokyo"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
CATEGORIES = [("1052522", "ブレンド"), ("1052523", "ストレート"), ("2426845", "ストレート")]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    time.sleep(REQUEST_INTERVAL)
    return resp.text


def fetch_listing() -> list[dict]:
    items, seen = [], set()
    for cbid, category in CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0" + (f"&page={page}" if page > 1 else "")
            html = fetch(url)
            for b in re.split(r'<li class="c-item-list__item">', html)[1:]:
                b = b.split("</li>")[0]
                n = re.search(r'class="c-item-list__ttl">(.*?)</div>', b, flags=re.S)
                pid = re.search(r"pid=(\d+)", b)
                if not n or not pid or pid.group(1) in seen:
                    continue
                seen.add(pid.group(1))
                p = re.search(r'class="c-item-list__price">(.*?)</div>', b, flags=re.S)
                ptxt = re.sub(r"<[^>]+>", "", p.group(1)) if p else ""
                pm = re.search(r"税込\s*([\d,]+)円", ptxt)
                items.append({
                    "pid": pid.group(1),
                    "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", n.group(1))).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "sold_out": bool(re.search(r"SOLD ?OUT|売り切れ", b, re.I)),
                    "category": category,
                })
            if re.search(r"page=%d\b" % (page + 1), html):
                page += 1
            else:
                break
    return items


def fetch_detail(pid: str):
    html = fetch(f"{BASE_URL}/?pid={pid}")
    m = re.search(r'sales:\s*"[\d,]+円\(税込\s*([\d,]+)円\)"', html)
    price = int(m.group(1).replace(",", "")) if m else None
    desc = None
    d = re.search(r"Detail\s*</[^>]+>(.*?)(?:</div>|<!--)", html, flags=re.S)
    return price, desc


def build_record(it: dict) -> dict:
    title = it["title"]
    wm = re.search(r"(\d+)\s*[gｇ]\s*$", title)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"\s*\d+\s*[gｇ]\s*$", "", title).strip()
    parsed = parse_product(name)
    if it["category"] == "ブレンド" or "ブレンド" in name:
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
    sold_out = it["sold_out"]
    status = "販売中"
    if sold_out:
        status = "終売" if it.get("discontinued") else "一時的に品切れ"
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
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": weight,
        "stock_status": status,
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={it['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in fetch_listing():
        if it["price"] is None:
            # SOLD OUT は一覧に価格が出ないので詳細ページの販売価格を使う
            it["price"], _ = fetch_detail(it["pid"])
            # マイルストーン・ブレンドは「6月末までの限定販売(予定)…早期終売」と詳細ページに明記
            it["discontinued"] = "マイルストーン" in it["title"]
        records.append(build_record(it))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ebonycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ebonycoffee.json に出力しました")


if __name__ == "__main__":
    main()
