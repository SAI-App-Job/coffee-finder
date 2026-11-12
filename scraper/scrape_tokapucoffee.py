# -*- coding: utf-8 -*-
"""
scrape_tokapucoffee.py

トカプコーヒー(TOKAPU COFFEE ROASTERY。北海道河西郡中札内村大通南6丁目13-1、カラーミーショップ tokapu.shop-pro.jp)の
自家焙煎コーヒー豆を取得する。

【対象】トップページに並ぶ商品のうち、商品名が「～珈琲豆(産地/銘柄 または ブレンド名 200g)」の単品9種(各200g)。
珈琲バッグ10個セット・珈琲豆お試し3種セット・お任せ3種セットは対象外。
【価格】オプション「コーヒー豆の状態」の先頭「豆のまま」の税込価格(全て2,400円)。
【商品名】店の商品名は「甘い香りの浅煎り珈琲豆(エチオピア/ブルーナイル200g)」のような宣伝文付きのため、
括弧内の「産地 銘柄 200g」を raw_name とし、焙煎度は括弧の前の宣伝文(浅煎り/中煎り/中深煎り/深煎り/極深煎り)から取る。
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
    "name": "トカプコーヒー",
    "url": "https://tokapu.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道河西郡中札内村大通南6丁目13-1",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ tokapu.shop-pro.jp のトップページと各商品ページを2026-10-26に確認。"
                   "特定商取引法表記(販売業者 トカプ コーヒー、運営統括責任者 木村務、中札内村大通南6丁目13-1)。"
                   "公式サイト r.goope.jp/tokapu/ に「自家焙煎スペシャルティ専門のコーヒーショップです」、"
                   "「自家焙煎の珈琲豆をネットショップでご購入いただけます」、所在地・定休日(水木金・不定休)の記載。"
                   "ショップ側のお知らせは2026-04-07(価格改定 4/1~)まで。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://tokapu.shop-pro.jp/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
ROAST_RE = re.compile(r"(極深煎|中深煎|中浅煎|深煎|浅煎|中煎)")
NAME_RE = re.compile(r"珈琲豆\((.+?)\)$")


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
    lines = [norm(l) for l in soup.get_text("\n", strip=True).split("\n") if l]
    idx = [i for i, l in enumerate(lines) if l == title]
    if not idx:
        return None
    seg = []
    for l in lines[idx[-1] + 1:]:
        if re.search(r"円\(内税\)", l):
            break
        seg.append(l)
    # 先頭の「産地(商品名:銘柄 200g)」「ブレンド名 200g」だけの見出し行は説明文ではないので除く
    for k in range(min(2, len(seg))):
        if "商品名" in seg[k]:
            seg = seg[k + 1:]
            break
    else:
        if seg and "200g" in seg[0] and len(seg[0]) <= 60:
            seg = seg[1:]
    return " ".join(seg)[:300] or None


def build(pid):
    url = BASE_URL + "?pid=" + pid
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    title = norm(p["name"])
    mm = NAME_RE.search(title)
    if "セット" in title or not mm:
        return None
    raw = mm.group(1).replace("/", " ")
    raw = re.sub(r"\(商品名[:：]\s*(.+)\)", r"\1", raw)
    variants = p.get("variants") or []
    beans = [v for v in variants if (v.get("option1_value") or "").strip() == "豆のまま"] or variants
    price = beans[0]["option_price_including_tax"] if beans else p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    wm = re.search(r"(\d+)\s*g", raw, re.I)
    weight = int(wm.group(1)) if wm else None
    rm = ROAST_RE.search(title.split("珈琲豆")[0])
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
        "flavor_notes": get_desc(html, title),
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
    with open("data_tokapucoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokapucoffee.json に出力しました")


if __name__ == "__main__":
    main()
