# -*- coding: utf-8 -*-
"""
scrape_goodcoffeelabo.py

GOOD COFFEE LABO(グッドコーヒーラボ、長崎県佐世保市元町1-33、販売業者
「Good Coffee Labo 牛島政則」、カラーミーショップ/独自ドメイン
goodcoffeelabo.jp)の商品情報を取得する。

【商品選別】
全商品検索(?mode=srh&cid=&keyword=、2ページ)で16件。うち「ドリップバッグ」
1件を除外し、豆15種(シングル13、French Blend、Caffeineless[デカフェ])を採用。
各商品は「100g - ○○円」「200g - ○○円」×「豆/粉」のバリエーションで、
豆/粉は同一商品のため、最小重量(100g)・豆のままを代表とする。

【焙煎度】商品名先頭の【浅煎り】【中煎り】【やや深煎り】【深煎り】から取得。
「やや深煎り」はアプリ上の統一表記として「中深煎り」に寄せる。

【産地】商品名に国名が無いため、サイト自身の産地別グループページ
(トップの産地バナー → ?mode=grp&gid=…、ページタイトルが国名)から
「pid → 国名」を引く。グループに属さない商品(Finca El Morito Gesha、
French Blend、Caffeineless)は産地 null のまま(推測しない)。

【在庫】カラーミー側は在庫管理なし(inventory_control: none)で売り切れ表示が
無いため、販売中として扱う。

robots.txt確認済み(2026-10-18): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "GOOD COFFEE LABO",
    "url": "https://goodcoffeelabo.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "長崎県佐世保市元町1-33",
    "prefecture": "長崎県",
    "robots_txt_status": "許可(2026-10-18確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://goodcoffeelabo.jp/"
LIST_URL = BASE_URL + "?mode=srh&cid=&keyword=&page={page}"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 2

NON_BEAN_KEYWORDS = ["ドリップバッグ", "セット", "ギフト"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PREFIX = re.compile(r"^【([^】]+)】")
ROAST_MAP = {"浅煎り": "浅煎り", "中煎り": "中煎り", "やや深煎り": "中深煎り", "深煎り": "深煎り"}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        soup = fetch_page(LIST_URL.format(page=page))
        added = 0
        for li in soup.select("li.c-item-list__item"):
            a = li.select_one(".c-item-list__ttl a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            added += 1
            items.append({"raw_name": a.get_text(strip=True), "pid": m.group(1),
                          "product_url": f"{BASE_URL}?pid={m.group(1)}"})
        time.sleep(CRAWL_DELAY_SECONDS)
        if added == 0:
            break
    return items


def scrape_origin_map() -> dict[str, str]:
    """産地別グループページ(トップの a.anchor[href*=mode=grp])から pid -> 国名。"""
    top = fetch_page(BASE_URL)
    gids = []
    for a in top.select("a.anchor[href*='mode=grp']"):
        m = re.search(r"gid=(\d+)", a.get("href", ""))
        if m and m.group(1) not in gids:
            gids.append(m.group(1))
    origin = {}
    for gid in gids:
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            soup = fetch_page(f"{BASE_URL}?mode=grp&gid={gid}")
        except requests.HTTPError:
            continue  # 商品の無いグループ(パナマ)は404が返る
        title = soup.title.get_text(strip=True) if soup.title else ""
        country = title.split(" - ")[0].strip()
        for a in soup.select("li.c-item-list__item .c-item-list__ttl a"):
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if m:
                origin[m.group(1)] = country
    return origin


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if m:
            try:
                return json.loads(m.group(1)).get("product")
            except json.JSONDecodeError:
                return None
    return None


def smallest_variant(variants: list[dict]) -> tuple[int | None, int | None]:
    """(重量g, 税込価格)。最小重量・豆のまま(先頭)を代表にする。"""
    best = None
    for v in variants:
        m = WEIGHT_PATTERN.search(v.get("option1_value") or "")
        if not m:
            continue
        w = int(m.group(1))
        if best is None or w < best[0]:
            best = (w, v.get("option_price_including_tax"))
    return best if best else (None, None)


def extract_texts(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    sub = soup.select_one("div.p-product-info__explain")
    exp = soup.select_one("div.p-product-explain p.explain")
    return (sub.get_text(" ", strip=True) if sub else None,
            exp.get_text(" ", strip=True) if exp else None)


def build_record(it: dict, origin_map: dict) -> dict | None:
    soup = fetch_page(it["product_url"])
    cp = extract_colorme_product(soup)
    if not cp:
        return None
    title = (cp.get("name") or it["raw_name"]).strip()
    weight, price = smallest_variant(cp.get("variants") or [])
    if price is None:
        price = cp.get("sales_price_including_tax")
    sub, explain = extract_texts(soup)
    parsed = parse_product(title)
    m = ROAST_PREFIX.match(title)
    roast = ROAST_MAP.get(m.group(1)) if m else parsed["roast_level"]
    stock_status = detect_stock_status(title)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "japanese_name": sub,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"] or origin_map.get(it["pid"]),
        "origin_source": parsed["origin_source"] or ("サイトの産地別グループ" if origin_map.get(it["pid"]) else None),
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "flavor_notes": explain,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": it["product_url"],
    }


def scrape_all_products():
    records, excluded = [], []
    items = scrape_list()
    origin_map = scrape_origin_map()
    for it in items:
        if any(k in it["raw_name"] for k in NON_BEAN_KEYWORDS):
            excluded.append({"shop_name": SHOP_INFO["name"], "raw_name": it["raw_name"],
                             "non_bean": True, "product_url": it["product_url"]})
            continue
        try:
            rec = build_record(it, origin_map)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {it['product_url']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": [],
              "non_bean_products_excluded": excluded}
    with open("data_goodcoffeelabo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_goodcoffeelabo.json に出力しました"
          f"(非コーヒー豆{len(excluded)}件は別枠に分離)")
