# -*- coding: utf-8 -*-
"""
scrape_morinocoffee.py

MORINO COFFEE(morino-coffee.net、滋賀県蒲生郡日野町松尾5丁目13-2、自家焙煎豆
のオンライン販売)の商品情報を取得する。WordPress+Welcart(usces)。

robots.txt確認済み(2026-10-11): User-agent: *に対し/wp-admin/のみDisallow。

【商品一覧】/category/item/ (2ページ)にコーヒー豆・アーモンド・送料案内
ページが混在して21件。商品コードがb始まりのうち、アーモンド(ナッツ)は豆では
ないため除外し、送料案内(t016)も除外。残る16件がコーヒー豆。

【価格・重量・焙煎度について】
実データ確認済み: 各商品ページのSKUは「商品コード-100」で、価格(税込)は
100gあたりの単価。販売は200gから発送(特商法表記「販売数量 200gより発送」、
商品名の「※200ｇから焙煎」)だが、SKU単位は100gなので代表は100g・単価とする。
焙煎度は購入時にお客様が選ぶ方式(ミディアム〜フレンチ)で固定値が無いため
null(roast_level)。原産国は商品ページの「原産国」欄(itemFrom)から取得する。
"""
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, detect_country_name

SHOP_INFO = {
    "name": "MORINO COFFEE",
    "url": "https://morino-coffee.net/",
    "platform": "Welcart(WordPress)",
    "address": "滋賀県蒲生郡日野町松尾5丁目13-2",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(2026-10確認。/wp-admin/のみDisallow)",
}
LIST_URLS = ["https://morino-coffee.net/category/item/", "https://morino-coffee.net/category/item/page/2/"]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
OUT_STATES = ("売切れ", "売り切れ", "入荷待ち", "品切れ")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def fetch_urls():
    urls = []
    for u in LIST_URLS:
        s = BeautifulSoup(get(u), "html.parser")
        for a in s.select("a[href]"):
            h = a["href"]
            if re.match(r"https://morino-coffee\.net/20\d\d/\d\d/", h) and h not in urls:
                urls.append(h)
    return urls


def clean_name(h1):
    n = re.split(r"[※]|　予約|\s{2,}", h1)[0]
    return re.sub(r"[\s　]+", " ", n).strip()


def flavor_from_desc(el):
    if el is None:
        return None
    paras = []
    for p in el.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t or t.startswith("※"):
            continue
        paras.append(t)
    t = " ".join(paras)
    t = re.sub(r"\s+", " ", t)
    return t[:200] or None


def build_record(url, html):
    s = BeautifulSoup(html, "html.parser")
    h1 = s.select_one("h1.item_name")
    code_el = s.select_one("dl.itemCode dd")
    if not h1 or not code_el:
        return None
    code = code_el.get_text(strip=True).lower().replace("ｂ", "b")
    full = h1.get_text(" ", strip=True)
    if not code.startswith("b") or "アーモンド" in full:
        return None
    name = clean_name(full)
    from_el = s.select_one("dl.itemFrom dd.from")
    origin = from_el.get_text(strip=True) if from_el else None
    price_m = re.search(r"[\d,]+", s.select_one(".field_price").get_text()) if s.select_one(".field_price") else None
    price = int(price_m.group(0).replace(",", "")) if price_m else None
    z = s.select_one(".zaiko span")
    stock_txt = z.get_text(strip=True) if z else ""
    out = any(k in stock_txt for k in OUT_STATES)
    parsed = parse_product(name)
    stock = detect_stock_status(name, out)
    desc = s.select_one(".productDesc")
    parsed_origin = parsed["origin_country"] or origin
    origin_src = parsed["origin_source"] or ("itemFrom" if origin else None)
    if not parsed_origin and desc is not None:
        # 原産国欄が無い商品(ブルンジ・ミャンマー)は説明文中の国名から補完
        d = detect_country_name(desc.get_text(" ", strip=True))
        if d:
            parsed_origin, origin_src = d, "description"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed_origin,
        "origin_source": origin_src,
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_from_desc(desc),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": url,
    }


if __name__ == "__main__":
    records = []
    for u in fetch_urls():
        rec = build_record(u, get(u))
        if rec:
            records.append(rec)
    with open("data_morinocoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_morinocoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:40])
