# -*- coding: utf-8 -*-
"""
scrape_hashimotocoffee.py

はしもと珈琲(自家焙煎珈琲豆販売・喫茶 はしもと珈琲、京都府京都市北区紫野西野町31-1、FC2ショッピングカート
hashimotocoffee.cart.fc2.com)の商品情報を取得する。東京都荒川区の同名店とは別店。

【対象】カテゴリ「レギュラーコーヒー」(/?ca=1、18件)のうち、200g入り袋の豆(ブレンド7+ストレート8)。
豆/粉は購入時に選べるため豆のままを代表とする(価格は共通)。除外: カップオンコーヒー・同10個セット(ドリップ個包装)、
リキッドコーヒー、ギフトセット、コーヒー用品、羊羹。重量は各商品ページの「200g入り袋単位の販売」から取る。
焙煎度は商品ページ冒頭の「やや深煎りです。」等の記述(「やや深煎り」=中深煎り)から取る。
在庫はバリエーション選択肢の data-submit(0=購入不可)で判定。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "はしもと珈琲",
    "url": "https://hashimotocoffee.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "京都府京都市北区紫野西野町31-1",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。robots.txtは/cancel/・/setup/・/tools/のみ禁止)",
    "source_note": "FC2カート https://hashimotocoffee.cart.fc2.com/ のカテゴリ「レギュラーコーヒー」と各商品ページを2026-10-21に確認。価格は「令和7年12月1日より商品価格を改定」(公式サイトお知らせ)後の価格。店舗情報は https://hashimotocoffee.web.fc2.com/store.html",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://hashimotocoffee.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 1.6
EXCLUDE = ("カップオン", "セット", "ギフト")
ROAST_RE = re.compile(r"(やや深煎り|やや浅煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_MAP = {"やや深煎り": "中深煎り", "やや浅煎り": "中浅煎り"}
NAME_ORIGIN = {"サントスNo.2": "ブラジル", "ジャワロブスターWIB-1": "インドネシア"}
WEIGHT_RE = re.compile(r"(\d+)\s*g入り")

_last = [0.0]


def fetch(url, post=None):
    wait = INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    if post:
        resp = requests.post(url, data=post, headers=REQUEST_HEADERS, timeout=30)
    else:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    _last[0] = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def scrape_list():
    html = fetch(f"{BASE_URL}/?ca=1", post={"par_page": "100", "Submit_par": "設定"})
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select("li.item"):
        a = li.select_one("dt.name a")
        p = li.select_one("dd.price")
        if not a or not p:
            continue
        name = a.get_text(strip=True)
        if any(k in name for k in EXCLUDE):
            continue
        pm = re.search(r"([\d,]+)円", unicodedata.normalize("NFKC", p.get_text()))
        opts = [o for o in li.select("select.variation_width option") if o.get("value") != "not_selected"]
        if not pm or not opts:
            continue
        bean = [o for o in opts if o.get_text(strip=True) == "豆"] or opts
        c = li.select_one("dd.comment")
        items.append({
            "name": name,
            "href": a["href"],
            "price": int(pm.group(1).replace(",", "")),
            "sold_out": all(o.get("data-submit") == "0" for o in bean),
            "comment": c.get_text(strip=True) if c else None,
        })
    return items


def fetch_detail(href):
    html = fetch(BASE_URL + href)
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    a = text.find("\n", text.find("レギュラーコーヒー", 0))
    b = text.find("価格：")
    body = text[a:b] if a >= 0 and b > a else text
    wm = WEIGHT_RE.search(body)
    lm = re.search(r"焙煎度合い\s*[:：]\s*(\S+)", body)  # 「□ 焙煎度合い : 中煎り」の明記を優先
    rm = ROAST_RE.search((lm.group(1) if lm else "").replace("中~深", "中深")) or ROAST_RE.search(body)
    roast = None
    if rm:
        roast = ROAST_MAP.get(rm.group(1), rm.group(1))
    return (int(wm.group(1)) if wm else None), roast


def build_record(it, weight, roast):
    name = it["name"]
    parsed = parse_product(name)
    is_blend = "ブレンド" in name or "BLEND" in name.upper()
    if is_blend:
        category, origin, origin_source, brand = "ブレンド", None, None, None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        category = parsed["category"]
        origin = parsed["origin_country"]
        origin_source = parsed["origin_source"]
        brand = parsed["designated_brand"]
        origin = NAME_ORIGIN.get(name, origin)
        if origin == "グァテマラ":
            origin = "グアテマラ"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": brand,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": it["comment"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": weight,
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": BASE_URL + it["href"],
    }


def scrape_all_products():
    records = []
    for it in scrape_list():
        weight, roast = fetch_detail(it["href"])
        records.append(build_record(it, weight, roast))
    return records


def main():
    records = scrape_all_products()
    with open("data_hashimotocoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hashimotocoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"])


if __name__ == "__main__":
    main()
