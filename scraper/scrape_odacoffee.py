# -*- coding: utf-8 -*-
"""
scrape_odacoffee.py

自家焙煎 おだ珈琲(福岡県嘉麻市鴨生240、味よし食堂の二階。1976年開店。オンラインショップ
www.odacoffee.com、カラーミーショップ)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「コーヒー豆」(cbid=377786, csid=0)の全商品(12商品: オリジナルブレンド3、
ストレート豆、農園・地区指定スペシャリティ豆)。ふるさと納税ポータルは別ページ・別サイトのため
対象外(重複させない)。
【価格・重量】販売数量は100g単位(特定商取引法ページ「100g単位でお受けいたします」、
商品ページの購入数欄「N ×100g」)で、表示価格は100gあたり。したがって weight_g=100。
挽き方のバリエーションは全て同一価格なので「豆のまま」を代表とする。
【文字コード】EUC-JP。在庫はvar Colorme の stock_num が0以下なら品切れ(None=無制限)。
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
    "name": "自家焙煎 おだ珈琲",
    "url": "https://www.odacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県嘉麻市鴨生240",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ www.odacoffee.com のカテゴリ「コーヒー豆」と各商品ページを2026-10-20に確認。"
                   "特定商取引法表記(販売業者「自家焙煎 おだ珈琲」、福岡県嘉麻市鴨生240)、お店のご案内(実店舗・喫茶、味よし食堂の二階)、"
                   "トップに「1976年開店以来…日々焙煎」と記載。ふるさと納税ポータルにも出品があるが自社ECを採用。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.odacoffee.com/"
LIST_URL = BASE_URL + "?mode=cate&cbid=377786&csid=0"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
LABEL_RE = re.compile(r"(原産国|生産地域|規格|品種|精製方法|乾燥方法|標高|収穫時期)：([^\n]+)")
EXCLUDE = ["ドリップ", "セット", "ギフト", "福袋"]


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(html, "html.parser"), html


def list_items():
    soup, _ = fetch(LIST_URL)
    items = []
    for li in soup.select("li.product-list__unit"):
        a = li.select_one("a.product-list__name")
        if not a:
            continue
        name = a.get_text(strip=True)
        if any(k in name for k in EXCLUDE):
            continue
        e = li.select_one(".product-list__expl")
        items.append((a["href"], name, e.get_text(" ", strip=True) if e else None))
    return items


def build(href, list_name, list_expl):
    url = BASE_URL + href
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    name = p["name"].strip()
    variants = p.get("variants") or []
    whole = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")] or variants
    price = whole[0]["option_price_including_tax"] if whole else p["sales_price_including_tax"]

    cat_text = ""
    for e in soup(["script", "style"]):
        e.decompose()
    node = soup.find(string=re.compile("原産国：|生産地域："))
    body = ""
    if node:
        blk = node.find_parent("div", class_="row") or node.find_parent("div")
        for br in blk.find_all("br"):
            br.replace_with("\n")
        body = blk.get_text("\n", strip=True)
    labels = {k: v.strip() for k, v in LABEL_RE.findall(body)}
    text_lines = [l for l in body.split("\n") if l and not LABEL_RE.match(l)]
    desc = " ".join(text_lines)[:300] or list_expl

    parsed = parse_product(name)
    is_blend = "ブレンド" in name or name in ("フレンチ",) or "ブレンド" in (list_expl or "")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if labels.get("原産国"):
            c = detect_country_name(labels["原産国"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if not parsed["origin_country"]:
            c = detect_country_name(name) or detect_country_name(list_expl or "")
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if labels.get("精製方法"):
            parsed["processing_method"] = normalize_processing_method(labels["精製方法"])

    roast_hint = None
    for kw in ("中深煎り", "中浅煎り", "深煎り", "浅煎り", "中煎り"):
        if kw in (list_expl or "") or kw in (desc or ""):
            roast_hint = kw
            break
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    farm = "、".join(f"{k}: {labels[k]}" for k in ("生産地域", "規格", "品種", "標高", "収穫時期") if labels.get(k)) or None
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
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    items = list_items()
    print(f"[info] 対象 {len(items)}件")
    records = []
    for href, name, expl in items:
        time.sleep(DELAY)
        try:
            rec = build(href, name, expl)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {href} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_odacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_odacoffee.json に出力しました")


if __name__ == "__main__":
    main()
