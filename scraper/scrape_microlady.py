# -*- coding: utf-8 -*-
"""
scrape_microlady.py

MICRO-LADY COFFEE STAND(microlady.shop-pro.jp、公式 micro-lady.jp、
滋賀県彦根市古沢町40-2 JR彦根駅構内、自家焙煎スペシャルティコーヒー)の
商品情報を取得する。カラーミーショップ(shop-pro.jp)、文字コードEUC-JP。

address: 公式サイトの店舗案内(about.html)・特定商取引法表示に「店舗住所
〒522-0007 滋賀県彦根市古沢町40-2 JR彦根駅構内」と明記されているため、
運営会社(合同会社MICRO-LADY)の本社住所(彦根市南川瀬町1409番地17)ではなく
店舗の所在地を採用する。

robots.txt確認済み(2026-10-11): User-agent: *は/secure/と/cart/のみ制限。

【対象商品】カテゴリ「コーヒー豆」(cbid=1641901)の40件のうち、器具・グッズ・
雑貨・ドリップバッグ(1杯分)を除く、名前に【100g】または【200g】が付く焙煎豆。
同じ銘柄が100g/200gの別商品(別pid)で並ぶため、最小重量(100g)を代表とする。
商品ページに説明文は無く(名前・価格・挽き方のみ)、焙煎度は商品名の
【深煎り】(アニバーサリーブレンドのみ)から取る。在庫はColormeのvariants
のstock_numで判定する。
"""
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "MICRO-LADY COFFEE STAND",
    "url": "https://microlady.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "滋賀県彦根市古沢町40-2 JR彦根駅構内",
    "prefecture": "滋賀県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}
BASE_URL = "https://microlady.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=1641901&csid=0&sort=n"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
PREFIX_RE = re.compile(r"^【(?:13th/)?(\d+)\s*[gｇ]】\s*")
NON_BEAN_KEYWORDS = ["ドリップバッグ"]
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "euc-jp"
    return r.text


def list_bean_items():
    s = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items, seen = [], set()
    for a in s.select('a[href*="pid="]'):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name or href in seen:
            continue
        seen.add(href)
        if any(k in name for k in NON_BEAN_KEYWORDS):
            continue
        m = PREFIX_RE.match(name)
        if not m:
            # 【13th/100g】 は PREFIX_RE で扱う。重量表記が無いものは豆ではない(器具・グッズ等)
            m2 = re.match(r"^【13th/(\d+)g】", name)
            if not m2:
                continue
            m = m2
        items.append({"href": href, "name": name, "weight": int(m.group(1)),
                      "clean": re.sub(r"\s+", " ", PREFIX_RE.sub("", name)).strip()})
    return items


def colorme_product(html):
    m = COLORME_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("product")
    except json.JSONDecodeError:
        return None


def build_record(item):
    url = BASE_URL + item["href"] if item["href"].startswith("?") else item["href"]
    p = colorme_product(fetch(url)) or {}
    variants = p.get("variants") or []
    whole = next((v for v in variants if "豆のまま" in (v.get("option1_value") or "")), variants[0] if variants else None)
    price = whole.get("option_price_including_tax") if whole else None
    if price is None:
        price = p.get("sales_price")
    nums = [v.get("stock_num") for v in variants if isinstance(v.get("stock_num"), int)]
    structural_out = bool(nums) and all(n <= 0 for n in nums)
    name = re.sub(r"\s+", " ", item["clean"])
    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
    stock = detect_stock_status(name, structural_out)
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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": item["weight"],
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": url,
    }


if __name__ == "__main__":
    best = {}
    for it in list_bean_items():
        k = it["clean"]
        if k not in best or it["weight"] < best[k]["weight"]:
            best[k] = it
    records = [build_record(it) for it in best.values()]
    with open("data_microlady.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_microlady.json に出力しました")
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], r["product_url"])
