# -*- coding: utf-8 -*-
"""
scrape_cafehanz.py

カフェハンズ(自家焙煎珈琲カフェハンズ、神奈川県横浜市中区根岸町3-143、2008-05-09開店。
オンラインショップ www.cafehanz.com、ショップサーブ)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「コーヒー豆(全種)」(/SHOP/267689/t02/list.html、list2.html、list3.html、全23件)のうち
単品の豆(ブレンド・ストレート・デカフェ)。セット・詰め合わせ(ST*、G*)・飲み比べ・ギフトは除外。
【重量・焙煎度】各商品ページ本文の「＜深煎：１００ｇ＞」の表記から焙煎度と内容量(100g)を取得する。
【価格・在庫】商品ページの税込価格(「豆/粉」の選択肢は同額で、豆を代表)。ショップサーブの商品ページの
バリエーション在庫情報(arrVari)と「品切れ」「売切れ」表記で在庫を判定する。
【文字コード】UTF-8(ヘッダ上はISO-8859-1扱いのため content を明示的に UTF-8 でデコード)。
robots.txt は 404(制限なし)。
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
    "name": "カフェハンズ",
    "url": "https://www.cafehanz.com/",
    "platform": "ショップサーブ",
    "address": "神奈川県横浜市中区根岸町3-143",
    "prefecture": "神奈川県",
    "robots_txt_status": "制限なし(2026-10-21確認。robots.txt は404)",
    "source_note": "ショップサーブ www.cafehanz.com のカテゴリ「コーヒー豆(全種)」と各商品ページを2026-10-21に確認。"
                   "特定商取引法に関する表示(販売業者 カフェハンズ、販売責任者 佐藤円、神奈川県横浜市中区根岸町3-143、許認可 喫茶営業許可、"
                   "TEL 045-625-3922、定休日 木曜・第3水曜)。トップに「自家焙煎珈琲の通販ならカフェハンズ」"
                   "「2008年5月9日開店当日」「焙煎機はバッハが開発したマイスター5kg」、店長日記・カレンダー・店頭告知あり。"
                   "ブランド商品の更新日は商品ごとに不明、トップのお知らせは2026-10-01の価格改定。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://www.cafehanz.com"
LIST_URLS = [BASE_URL + "/SHOP/267689/t02/list%s.html" % ("" if p == 1 else p) for p in (1, 2, 3)]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
EXCLUDE = ["セット", "ギフト", "詰め合わせ", "詰合せ", "飲み比べ", "お試し", "福袋"]
SPEC_RE = re.compile(r"[＜<]\s*([^：:＞>]+?)\s*[：:]\s*(\d+)\s*[gｇ]\s*[＞>]")
ROAST_MAP = {"浅煎": "浅煎り", "中煎": "中煎り", "中深煎": "中深煎り", "深煎": "深煎り", "極深煎": "極深煎り",
             "中浅煎": "中浅煎り"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.content.decode("utf-8", errors="replace"), "html.parser"), r.content.decode("utf-8", errors="replace")


def list_items():
    items = {}
    for url in LIST_URLS:
        soup, _ = fetch(url)
        main = soup.select_one("div.mainCont") or soup
        for a in main.select("h2.goods a"):
            href = a["href"]
            if href not in items:
                items[href] = a.get_text(strip=True)
        time.sleep(DELAY)
    return items


def build(href, list_name):
    url = BASE_URL + href
    soup, html = fetch(url)
    h2 = soup.select_one("h2.red")
    name = unicodedata.normalize("NFKC", (h2.get_text(strip=True) if h2 else list_name)).strip()
    name = re.sub(r"\s+", " ", name)
    pe = soup.select_one("p.price")
    pm = re.search(r"([\d,]+)\s*円", pe.get_text()) if pe else None
    if not pm:
        return None
    price = int(pm.group(1).replace(",", ""))
    main = soup.select_one("div.mainCont") or soup
    for t in main(["script", "style"]):
        t.decompose()
    for br in main.find_all("br"):
        br.replace_with("\n")
    text = main.get_text("\n", strip=True)
    head = text.split("拡大表示")[0]
    norm = unicodedata.normalize("NFKC", head)
    sm = SPEC_RE.search(head)
    roast, weight = None, None
    if sm:
        r = unicodedata.normalize("NFKC", sm.group(1))
        roast = ROAST_MAP.get(r) or r
        weight = int(sm.group(2))
    if not sm:
        # 「内容詳細」表(内容量・焙煎度)から取得(例: ハンズブレンド)。価格欄の旧価格は使わない
        nfull = unicodedata.normalize("NFKC", text)
        wm = re.search(r"内容量\s+(\d+)\s*g", nfull)
        rm = re.search(r"焙煎度\s+(\S+)", nfull)
        if wm:
            weight = int(wm.group(1))
        if rm:
            r = rm.group(1).strip()
            roast = ROAST_MAP.get(r) or r
    lines = [l for l in head.split("\n") if l.strip()
             and not SPEC_RE.search(l) and not l.startswith("<粉") and "極細挽き：" not in l]
    desc = " ".join(lines)[:300] or None
    sold_out = bool(re.search(r"品切れ|売り切れ|売切れ|在庫切れ|SOLD ?OUT", text[:len(head) + 400]))

    is_blend = "ブレンド" in name
    parsed = parse_product(name)
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
        parsed = apply_category_hint_fallback(parsed, name)
    if not parsed["processing_method"] and desc:
        parsed["processing_method"] = extract_from_description(desc)["processing_method"]
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
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def main():
    items = list_items()
    items = {h: n for h, n in items.items() if not any(k in n for k in EXCLUDE)}
    print(f"[info] 対象 {len(items)}件")
    records = []
    for href, name in items.items():
        time.sleep(DELAY)
        try:
            rec = build(href, name)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {href} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_cafehanz.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafehanz.json に出力しました")


if __name__ == "__main__":
    main()
