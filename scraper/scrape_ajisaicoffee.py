# -*- coding: utf-8 -*-
"""
scrape_ajisaicoffee.py

紫陽花珈琲(北海道札幌市中央区円山西町7丁目1-18、株式会社紫陽花珈琲。カフェ併設。
オンラインショップはカラーミーショップ ajisai-coffee.shop-pro.jp)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「COFFEE BEANS」(cbid=2787684)の単品8種。「ブレンドコーヒー4種アソートパック」
「ストレート4種アソートパック」と、カテゴリ「DRIP PACK」(ドリップパック)は対象外。
【価格】オプション「挽き方」の先頭「豆のまま」の税込価格(税別600~800円の税込表示)。
【重量】商品名に「100g」とある5商品は100g。名称に重量表記が無い3商品(カフェインレスブレンド/ブラジル No.2 S19/
イエメン モカ・マタリ9)は商品ページにも内容量の記載が無いため None。
【焙煎度】商品名の【極深煎】【中深煎】【浅煎】【深煎】のみ。ストレート豆は焙煎度の記載が無いため None。
【文字コード】EUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "紫陽花珈琲",
    "url": "https://ajisai-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市中央区円山西町7丁目1-18",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ ajisai-coffee.shop-pro.jp のカテゴリ「COFFEE BEANS」と各商品ページを2026-10-26に確認。"
                   "特定商取引法表記(株式会社紫陽花珈琲、運営統括責任者 和田直也、札幌市中央区円山西町7丁目1-18)。"
                   "公式サイトに「一杯ずつ丁寧に淹れる自家焙煎珈琲と、…リコッタパンケーキ」「〒064-0944 札幌市中央区円山西町7丁目1-18、"
                   "Open 11:00 Close 18:00、定休日 水曜日」、2026/6/1「HPをリニューアルしました」の記載。"
                   "名称に重量表記が無い3商品は内容量不明のため重量 None。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://ajisai-coffee.shop-pro.jp/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
BEANS_CBID = 2787684
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
ROAST_RE = re.compile(r"(極深煎|中深煎|中浅煎|深煎|浅煎|中煎)")
EXCLUDE = ["アソート", "ドリップ", "セット"]
# coffee_parser が判定できない銘柄の産地補完(商品名に明記)
ORIGIN_OVERRIDE = {"イエメン": "イエメン"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.content.decode("euc-jp", errors="replace")


def norm(s):
    s = unicodedata.normalize("NFKC", s.replace("　", " "))
    return re.sub(r"\s+", " ", s).strip()


def list_pids():
    html = fetch(BASE_URL)
    time.sleep(DELAY)
    pids = []
    for pid in re.findall(r"\?pid=(\d+)", html):
        if pid not in pids:
            pids.append(pid)
    return pids


def get_desc(html, title):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
    idx = [i for i, l in enumerate(lines) if norm(l) == title]
    if not idx:
        return None
    seg = []
    for l in lines[idx[0] + 1:]:
        if l == "販売価格":
            break
        seg.append(l)
    return norm(" ".join(seg))[:300] or None


def build(pid):
    url = BASE_URL + "?pid=" + pid
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    raw = norm(p["name"])
    if (p.get("category") or {}).get("id_big") != BEANS_CBID or any(w in raw for w in EXCLUDE):
        return None
    variants = p.get("variants") or []
    beans = [v for v in variants if (v.get("option1_value") or "").strip() == "豆のまま"] or variants
    price = beans[0]["option_price_including_tax"] if beans else p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    wm = re.search(r"(\d+)\s*g", raw, re.I)
    weight = int(wm.group(1)) if wm else None
    rm = ROAST_RE.search(raw)
    roast = (rm.group(1) + "り") if rm else None
    parsed = parse_product(raw)
    if "ブレンド" in raw:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, raw)
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDE.items():
                if kw in raw:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "manual"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": get_desc(html, raw),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    pids = list_pids()
    print(f"[info] 候補 {len(pids)}件")
    records = []
    for pid in pids:
        time.sleep(DELAY)
        try:
            rec = build(pid)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_ajisaicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ajisaicoffee.json に出力しました")


if __name__ == "__main__":
    main()
