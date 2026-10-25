# -*- coding: utf-8 -*-
"""
scrape_pioneercoffee.py

パイオニアコーヒー工房(神奈川県厚木市七沢2182-1、株式会社パイオニアコーヒー工房。
オンラインショップ pioneercoffee-factory.co.jp、カラーミーショップ)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「コーヒー豆」(cbid=1860592、全20商品・2ページ)のうち豆の商品。ドリップバッグ・
オリジナルリキッドアイスコーヒーは除外。コーヒー定期便・生豆・器具・ギフト・講座の各カテゴリは対象外。
【重量・価格】商品ページに内容量の文言が無く、購入数欄が「数量入力 + 『00ｇ』」(カート表示も「N00ｇ」)で、
送料の案内にも「100ｇ袋×4」とあるため、販売単位は100g(1個=100g)。オプション「形状」の先頭「豆」
(豆のまま)の税込価格を採用。重量は100gだが、商品ページ上に「100g」と明記された箇所は無い。
【焙煎度】商品名に「ミディアム」「フルシティ」とあるものだけ取得。他は不明のため None。
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
    "name": "パイオニアコーヒー工房",
    "url": "https://pioneercoffee-factory.co.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県厚木市七沢2182-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ pioneercoffee-factory.co.jp のカテゴリ「コーヒー豆」と各商品ページを2026-10-21に確認。"
                   "特定商取引法表記(株式会社パイオニアコーヒー工房、神奈川県厚木市七沢2182-1、TEL 046-281-8761)。"
                   "店舗受け取り・店舗払い可。テレビ東京「アド街ック天国」(2021-11-06放送 厚木七沢温泉郷)で2014年開店の焙煎所兼喫茶として紹介。"
                   "重量は購入数欄の単位表示(N00ｇ)と送料案内(100ｇ袋×4)から100gと判断。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://pioneercoffee-factory.co.jp/"
CAT_URL = BASE_URL + "?mode=cate&cbid=1860592&csid=0&page={page}"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
EXCLUDE = ["ドリップバッグ", "リキッド", "定期便", "講座", "セット", "ギフト"]


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(html, "html.parser"), html


def list_items():
    items = []
    for page in (1, 2):
        soup, _ = fetch(CAT_URL.format(page=page))
        for b in soup.select("div.item_box"):
            a = b.select_one("p.item_name a")
            if not a:
                continue
            name = a.get_text(strip=True)
            if any(k in name for k in EXCLUDE):
                continue
            items.append((a["href"], name))
        time.sleep(DELAY)
    return items


def clean_name(name):
    name = unicodedata.normalize("NFKC", name.replace("　", " "))
    return re.sub(r"\s+", " ", name).strip()


def build(href, list_name):
    url = BASE_URL + href
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    name = clean_name(p["name"])
    variants = p.get("variants") or []
    beans = [v for v in variants if (v.get("option1_value") or "").strip() == "豆"] or variants
    price = beans[0]["option_price_including_tax"] if beans else p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0

    d = soup.select_one("div.product_description")
    desc = None
    if d:
        for br in d.find_all("br"):
            br.replace_with("\n")
        desc = " ".join(l.strip() for l in d.get_text("\n", strip=True).split("\n") if l.strip())[:300] or None

    roast = None
    if "フルシティ" in name:
        roast = "フルシティロースト"
    elif "ミディアム" in name:
        roast = "ミディアムロースト"
    is_blend = "ブレンド" in name or "blend" in name.lower() or name.startswith("こよみ珈琲")
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
        if "ブルーマウンテンブレンド" in name:
            pass
    else:
        parsed["category"] = "ストレート"
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
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
    for href, name in items:
        time.sleep(DELAY)
        try:
            rec = build(href, name)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {href} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_pioneercoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pioneercoffee.json に出力しました")


if __name__ == "__main__":
    main()
