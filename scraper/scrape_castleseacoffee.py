# -*- coding: utf-8 -*-
"""
scrape_castleseacoffee.py

CASTLE SEA COFFEE(神奈川県小田原市。販売業者 有限会社ホライゾン、神奈川県小田原市国府津1725。
オンラインショップ csc-shop.com、カラーミーショップ)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「コーヒー豆 - ブレンド」(cbid=2549115)・「コーヒー豆 ‐ シングル」(2920643)・
「期間限定」(2775992)のうち豆の商品。ギフト・ドリップバッグ・リキッドコーヒー・水出し・雑貨・
コラボレーション商品(BLOCKHEAD COFFEE 他社ブランド、品切れ)は除外。同名商品(オータムブレンド)は1件に統合。
【重量・価格】各商品のオプションは「状態(豆のまま/粉)」×「内容量(100g/200g)」。最小重量=100gの
「豆のまま」の税込価格(内税)を採用(商品ページ記載「100g・2,060円/200g・3,990円」で確認)。
【焙煎度】商品ページには「浅煎り〜深煎り」のスライダー図(CSSの位置指定)のみで焙煎度の文言は無いため、
roast_level は None とし、スライダー位置(%)を roast_hint に記録する。
【在庫】オプション在庫は無制限(stock_num=None)、一覧に SOLD OUT 表示があれば品切れ。
【文字コード】EUC-JP。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "CASTLE SEA COFFEE",
    "url": "https://csc-shop.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県小田原市国府津1725",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ csc-shop.com のカテゴリ一覧と各商品ページを2026-10-21に確認。"
                   "特定商取引法表記(販売業者 有限会社ホライゾン、神奈川県小田原市国府津1725)、"
                   "ABOUT/トップに「神奈川県小田原市の自家焙煎コーヒー店」「日々焙煎しております」「豆は、ご注文を頂いてから焙煎」、"
                   "営業時間10:00〜17:00・休業日カレンダー。最新の更新は2026/10/06・2026/09/29。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://csc-shop.com/"
CATEGORIES = [(2549115, "ブレンド"), (2920643, "シングル"), (2775992, "期間限定")]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
EXCLUDE = ["ギフト", "ドリップ", "リキッド", "水出し", "セット", "マグ", "バッグ", "BLOCKHEAD"]
LABEL_RE = re.compile(r"(精\s*選\s*方\s*法|生産地域・農園|生産地域|品\s*種|標\s*高)\s*[：:]\s*([^\n]+)")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(html, "html.parser"), html


def list_items():
    items = {}
    names = set()
    for cb, cname in CATEGORIES:
        page = 1
        while True:
            soup, _ = fetch(f"{BASE_URL}?mode=cate&cbid={cb}&csid=0&page={page}")
            for li in soup.select("li.c-item-list__item"):
                a = li.select_one(".c-item-list__ttl a")
                if not a:
                    continue
                name = a.get_text(strip=True)
                if any(k in name for k in EXCLUDE) or name in names:
                    continue
                names.add(name)
                pid = re.search(r"pid=(\d+)", a["href"]).group(1)
                items[pid] = (name, cname, "SOLD OUT" in li.get_text(" ", strip=True))
            time.sleep(DELAY)
            if not any(f"page={page + 1}" in a.get("href", "") for a in soup.select("a")):
                break
            page += 1
    return items


def build(pid, list_name, cname, list_sold):
    url = f"{BASE_URL}?pid={pid}"
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    name = p["name"].replace("　", " ").strip()
    variants = p.get("variants") or []
    cand = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    cand = [v for v in cand if re.match(r"^\s*100\s*[gｇ]", v.get("option2_value") or "")]
    if not cand:
        print(f"[warn] 100g豆のままが無い: {name}")
        return None
    v = cand[0]
    price = v["option_price_including_tax"]
    stock = v.get("stock_num")
    out = list_sold or (isinstance(stock, int) and stock <= 0)

    ex = soup.select_one("div.p-product-explain__body")
    body, gray, slider = "", None, None
    if ex:
        gray_el = ex.find("div", style=re.compile("dcdcdc"))
        if gray_el:
            for br in gray_el.find_all("br"):
                br.replace_with("\n")
            gray = gray_el.get_text("\n", strip=True)
        sm = re.search(r"焙煎.*?left:\s*(\d+)%", str(ex), re.S)
        if sm:
            slider = int(sm.group(1))
        for br in ex.find_all("br"):
            br.replace_with("\n")
        body = ex.get_text("\n", strip=True)
    labels = {re.sub(r"\s+", "", k): val.strip() for k, val in LABEL_RE.findall(gray or body)}
    flavor_lines = [l for l in (gray or "").split("\n") if l and not LABEL_RE.match(l)]
    desc = " ".join(flavor_lines)[:300] or None

    is_blend = cname == "ブレンド" or "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(labels.get("生産地域・農園", "") or labels.get("生産地域", ""))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, name)
        if labels.get("精選方法") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(labels["精選方法"])
    farm = "、".join(f"{k}: {labels[k]}" for k in ("生産地域・農園", "生産地域", "品種", "標高") if labels.get(k)) or None
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
        "roast_hint": (f"焙煎スライダー位置{slider}%(0=浅煎り〜100=深煎り)" if slider is not None else None),
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": bool(out),
        "product_url": url,
    }


def main():
    items = list_items()
    print(f"[info] 対象 {len(items)}件")
    records = []
    for pid, (name, cname, sold) in items.items():
        time.sleep(DELAY)
        try:
            rec = build(pid, name, cname, sold)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_castleseacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_castleseacoffee.json に出力しました")


if __name__ == "__main__":
    main()
