# -*- coding: utf-8 -*-
"""
scrape_funakura.py

珈琲倶楽部 船倉(https://www.coffeefunakura.com/、鹿児島県薩摩川内市白和町4-12、
自家焙煎珈琲店。1988年創業)の自家焙煎コーヒー豆の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

robots.txt確認済み(2026-10): /secure/ と /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
カテゴリ「自家焙煎珈琲豆100g袋」(cbid=2798205)と「自家焙煎珈琲豆200g袋」(cbid=2798206)
の一覧(ページ送りあり)から商品を集める。同じ銘柄に100g袋と200g袋がある場合は、
最小重量(100g)を代表にする。セット(アイス珈琲1L×6本)・200gのみで100gのない商品は
銘柄ごとに最小重量を採るため、100gが存在すれば100gが選ばれる。

【価格・重量】
商品名末尾の「（100ｇ）」から重量を、商品ページの「販売価格」(税込、セール価格が
ある場合はセール価格)を採用する。「★セール★」付きの商品は名前から★セール★を除く。

【産地・焙煎度】
商品説明の「【生豆生産国】」から産地を取る(ブレンドは複数国のため blend_components)。
焙煎度は店頭表記なし(購入時の「豆を挽く/豆のまま」選択のみ)のため None。
"""

import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲倶楽部 船倉",
    "url": "https://www.coffeefunakura.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "鹿児島県薩摩川内市白和町4-12",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://www.coffeefunakura.com/"
CATEGORY_IDS = ["2798205", "2798206"]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["セット", "アイス珈琲", "ドリップ", "カップオン", "ギフト", "バラエティ"]

WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[ｇgＧG]\s*[）)]")
PRICE_PATTERN = re.compile(r"([\d,]+)円")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content.decode("euc-jp", errors="replace"), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def list_products() -> list[dict]:
    items, seen = [], set()
    for cbid in CATEGORY_IDS:
        for page in range(1, 10):
            url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0" + ("" if page == 1 else f"&page={page}")
            soup = fetch_soup(url)
            found = 0
            for box in soup.select("div.item_box"):
                a = box.select_one("p.item_name a")
                if not a:
                    continue
                m = re.search(r"pid=(\d+)", a.get("href", ""))
                name = clean(a.get_text())
                if not m or not name:
                    continue
                pid = m.group(1)
                found += 1
                if pid in seen:
                    continue
                seen.add(pid)
                items.append({"pid": pid, "name": name})
            time.sleep(CRAWL_DELAY_SECONDS)
            if not found:
                break
    return items


def parse_detail(pid: str) -> dict:
    url = f"{BASE_URL}?pid={pid}"
    soup = fetch_soup(url)
    name = clean(soup.select_one("h2.product_name").get_text())
    desc_el = soup.select_one("div.product_description")
    desc = re.sub(r"\n\s*\n+", "\n", desc_el.get_text()) if desc_el else ""
    price = None
    price_el = soup.select_one("table.add_cart_table strong.price")
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))
    text_all = soup.get_text(" ")
    sold_out = bool(re.search(r"売り切れ|SOLD ?OUT|在庫切れ", clean(soup.select_one("div.add_cart").get_text() if soup.select_one("div.add_cart") else "")))
    origin_m = re.search(r"【生豆生産国】\s*\n?\s*([^\n【]+)", desc)
    taste_m = re.search(r"【味の特長】\s*\n?\s*([^\n=＝※]+)", desc)
    lead = desc.strip().split("\n")[0] if desc.strip() else ""
    return {
        "url": url, "name": name, "price": price, "sold_out": sold_out,
        "origin_label": origin_m.group(1).strip() if origin_m else None,
        "taste": taste_m.group(1).strip() if taste_m else None,
        "lead": clean(lead),
        "desc_lines": [clean(l) for l in desc.split("\n") if clean(l) and not re.match(r"^[=＝]+$", clean(l))],
    }


def base_name(name: str) -> str:
    n = name.replace("★セール★", "")
    n = WEIGHT_PATTERN.sub("", n)
    return clean(n)


def build_record(d: dict, weight: int) -> dict | None:
    name = base_name(d["name"])
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    label = d["origin_label"] or ""
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        comps = [c for c in re.split(r"[・、,，]", label) if c.strip()]
    else:
        comps = []
        if not parsed["origin_country"]:
            c = detect_country_name(name) or detect_country_name(label)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, name)
    decaf = None
    if "デカフェ" in name:
        decaf = "カフェインを限りなく取り除いたノンカフェインコーヒー(除去方法の記載なし)"
    flavor = d["taste"]
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
        "roast_hint": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": d["lead"] if not is_blend and d["lead"] else None,
        "flavor_notes": flavor,
        "blend_components": comps,
        "decaf_process": decaf,
        "price": d["price"],
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if d["sold_out"] else "販売中",
        "out_of_stock": d["sold_out"],
        "product_url": d["url"],
    }


def scrape_all_products() -> list[dict]:
    # 銘柄ごとに最小重量のバリエーションを代表にする
    best: dict[str, tuple[int, dict]] = {}
    for it in list_products():
        if any(k in it["name"] for k in NON_BEAN_KEYWORDS):
            continue
        wm = WEIGHT_PATTERN.search(it["name"])
        if not wm:
            continue
        w = int(wm.group(1))
        key = base_name(it["name"])
        if key not in best or w < best[key][0]:
            best[key] = (w, it)
    records = []
    for key, (w, it) in best.items():
        try:
            d = parse_detail(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        rec = build_record(d, w)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_funakura.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_funakura.json に出力しました")


if __name__ == "__main__":
    main()
