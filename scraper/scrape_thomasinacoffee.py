# -*- coding: utf-8 -*-
"""
scrape_thomasinacoffee.py

トマシーナ珈琲(神奈川県横浜市栄区上郷町4491-22、販売責任者 佐々木雅彦。
オンラインショップ thomasinacoffee.ocnk.net、おちゃのこネット)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「珈琲豆」(product-list/2、20商品)の全商品。コーヒーシュガー・水出しアイスコーヒー・
CAFEC(器具)・14周年記念限定品(現在0件)は対象外。
【重量・価格】商品はすべて「生豆220g(トップページ表記は210g)を焙煎する」単位の注文焙煎で、焙煎後は水分が抜けて
1割前後(210g表記では180g前後)軽くなる、と店が明記している。weight_g には商品説明に明記された生豆のg数を入れ、
焙煎後重量が約1割少ないことを farm_note に記載する。価格は商品ページの税込「販売価格」
(希望小売価格はメーカー参考価格のため使わない)。
【焙煎度】購入時に備考欄で指定(ミディアム〜イタリアン)する注文焙煎のため roast_level は None。
【在庫】一覧の「[在庫なし]」を品切れとする(「[在庫わずか]」は販売中)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "トマシーナ珈琲",
    "url": "https://thomasinacoffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "神奈川県横浜市栄区上郷町4491-22",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。robots.txtはGPTBot等の生成AI系クローラのみ全面禁止で、それ以外は制限なし)",
    "source_note": "おちゃのこネット thomasinacoffee.ocnk.net のカテゴリ「珈琲豆」と各商品ページを2026-10-21に確認。"
                   "特定商取引法表示(販売主 トマシーナ珈琲、神奈川県横浜市栄区上郷町4491-22、電話045-894-7136)、"
                   "トップに「横浜にある小さな自家焙煎のお豆屋さん」「ご注文後に焙煎」「当店にお客様専用駐車場はありません」"
                   "「10月24日・25日の秋のセールは店舗でお引き渡し」とあり実店舗(引き取り)あり。"
                   "2026-10-21のお知らせ更新、14周年。重量は生豆基準(焙煎後は約1割減)。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://thomasinacoffee.ocnk.net"
LIST_URL = BASE_URL + "/product-list/2"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2.0
BLEND_NAMES = ("ブレンド",)


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_items():
    soup = BeautifulSoup(fetch_html(LIST_URL), "html.parser")
    items = []
    for td in soup.select("table.list_item_table td"):
        a = td.select_one("h2 a")
        if not a:
            continue
        pid = re.search(r"/product/(\d+)", a["href"]).group(1)
        price_el = td.select_one(".pricech")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        stock = td.select_one(".stock")
        items.append({
            "pid": pid,
            "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "sold_out": bool(stock and "在庫なし" in stock.get_text()),
        })
    return items


def build(item):
    pid = item["pid"]
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    box = soup.select_one("div.detail_desc_box")
    text = ""
    if box:
        for br in box.find_all("br"):
            br.replace_with("\n")
        text = box.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    wm = re.search(r"生豆\s*(\d+)\s*g", unicodedata.normalize("NFKC", text))
    weight = int(wm.group(1)) if wm else None
    # 販売価格/税込行を除いた説明
    desc_lines = [l for l in lines[1:] if not l.startswith("販売価格") and not re.match(r"^税込\s*\d", unicodedata.normalize("NFKC", l))]
    desc = " ".join(desc_lines)[:300] or None
    base = unicodedata.normalize("NFKC", item["name"])
    base = re.sub(r"\s+", " ", base).strip()
    is_blend = any(k in base for k in BLEND_NAMES)
    parsed = parse_product(base)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"] and desc:
            c = detect_country_name(desc)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, base)
    if not parsed["processing_method"] and desc:
        parsed["processing_method"] = extract_from_description(desc)["processing_method"]
    out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": "注文時に備考欄で焙煎度を指定(ミディアム〜イタリアン)",
        "flavor_notes": desc,
        "farm_note": f"生豆{weight}g分の価格。焙煎後は水分が抜けて1割前後軽くなる" if weight else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/product/{pid}",
    }


def main():
    items = list_items()
    print(f"[info] 対象 {len(items)}件")
    records = []
    for item in items:
        time.sleep(DELAY)
        try:
            records.append(build(item))
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {item['pid']} ({e})")
    with open("data_thomasinacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_thomasinacoffee.json に出力しました")


if __name__ == "__main__":
    main()
