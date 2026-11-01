# -*- coding: utf-8 -*-
"""
scrape_takanoniseko.py

高野珈琲店(北海道虻田郡ニセコ町有島126-90、公式 takano-coffee.com「小さな珈琲豆焙煎販売店」)の
商品情報を取得する。販売先は Yahoo!ショッピング店「しましま珈琲店」
(store.shopping.yahoo.co.jp/simasima/)。同ストアには猫雑貨・ハリオ等の器具・チョコ・
ドリップバッグ・リキッドアイスコーヒー等も同居するため、焙煎豆(商品名に「コーヒー豆」を含む cb*/ブレンド)だけを対象にする。

【プラットフォーム】
店舗の商品一覧(/search.html、2ページ目以降は ?page=N)は Next.js の `__NEXT_DATA__` JSON に
商品名・価格・URLが埋め込まれている(1ページ30件、全356件)。ショップ一覧の全ページを走査し、
商品ページの `item.stock.isAvailable` で在庫を判定する。
(店名は SHOP_INFO のとおり「高野珈琲店」。Yahoo!上の店名は「しましま珈琲店」で同一店。)

【重量・価格】
全て200g単位の1種類のみ(100g設定なし)。価格は一覧JSONの `price`(税込)。
豆のまま/粉は購入時の選択式(豆のままを基準)。同一産地でもロースト違いは別商品として別URLで販売されているため別銘柄として扱う。
"""

import html
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "高野珈琲店",
    "url": "https://store.shopping.yahoo.co.jp/simasima/",
    "platform": "Yahoo!ショッピング",
    "address": "北海道虻田郡ニセコ町有島126-90",
    "prefecture": "北海道",
    "robots_txt_status": "Yahoo!ショッピングのrobots.txt(https://store.shopping.yahoo.co.jp/robots.txt)で /search.html のクエリは strcid/brandid/spec/pt/pf 等のみ禁止。page指定のみ使用(許可)",
    "source_note": "Yahoo!ショッピング「しましま珈琲店」(https://store.shopping.yahoo.co.jp/simasima/)の商品一覧・商品ページを2026-10-26に確認。"
                   "公式 http://www.takano-coffee.com/ に「小さな珈琲豆焙煎販売店」「丁寧に焙煎」、住所ニセコ町有島126-90。"
                   "焙煎豆のみ対象(ドリップバッグ・リキッド・ゼリー・チョコ・器具・猫雑貨は除外)。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/simasima"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 3
MAX_PAGES = 12
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

EXCLUDE_KEYWORDS = ("ギフト", "ドリップバッグ", "リキッド", "ゼリー", "セット", "定期")
ROAST_WORDS = ("ライトロースト", "シナモンロースト", "ミディアムロースト", "ハイロースト", "シティロースト",
               "フルシティロースト", "フレンチロースト", "イタリアンロースト")
ORIGIN_OVERRIDES = {"グァテマラ": "グアテマラ"}


def fetch_list_items() -> list[dict]:
    items, seen = [], set()
    for p in range(MAX_PAGES):
        url = f"{BASE_URL}/search.html" if p == 0 else f"{BASE_URL}/search.html?page={p}"
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        if not m:
            break
        data = json.loads(m.group(1))
        groups = ((data["props"]["initialState"]["bff"] or {}).get("searchResults") or {}).get("items")
        if not groups:
            break
        added = 0
        for entries in groups.values():
            for entry in entries:
                content = entry.get("content") or {}
                if isinstance(content.get("items"), list):
                    for i in content["items"]:
                        u = (i.get("url") or "").split("?")[0]
                        if "name" in i and u and u not in seen:
                            seen.add(u)
                            items.append(i)
                            added += 1
        if added == 0:
            break
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def fetch_detail(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("utf-8")
    soup = BeautifulSoup(text, "html.parser")
    og = soup.select_one('meta[property="og:description"]')
    desc = None
    if og and og.get("content"):
        raw = html.unescape(og["content"])
        raw = raw.split("■この商品の配送")[0]
        desc = BeautifulSoup(raw.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
    available = True
    m = NEXT_DATA_PATTERN.search(text)
    if m:
        item = json.loads(m.group(1))["props"]["pageProps"].get("item") or {}
        available = bool((item.get("stock") or {}).get("isAvailable", True))
    return {"desc": desc, "available": available}


def clean_name(title: str) -> str:
    t = unicodedata.normalize("NFKC", title)
    roast = next((w for w in ROAST_WORDS if w in t), None)
    t = re.sub(r"【[^】]*】", " ", t)       # 【コーヒー豆 200g】【レターパック…】
    t = re.sub(r"\s*[A-F]$", "", t.strip())  # 末尾の送料区分記号
    t = t.replace("/", " ").replace("　", " ").replace("スペシャルティコーヒー", " ")
    for w in ROAST_WORDS:
        t = t.replace(w, " ")
    t = re.sub(r"\s+", " ", t).strip()
    if roast:
        t = f"{t} {roast}".strip()
    return t


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if "コーヒー豆" not in title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    url = (item.get("url") or "").split("?")[0]
    time.sleep(CRAWL_DELAY_SECONDS)
    detail = fetch_detail(url)

    norm_title = unicodedata.normalize("NFKC", title)
    wm = re.search(r"(\d+)\s*[gG]", norm_title)
    weight = int(wm.group(1)) if wm else None

    name = clean_name(title)
    for k, v in ORIGIN_OVERRIDES.items():
        name = name.replace(k, v)
    parsed = parse_product(name)
    explicit_roast = next((w for w in ROAST_WORDS if w in unicodedata.normalize("NFKC", title)), None)
    if explicit_roast:  # 「ハイツ農園」を「ハイ」ローストと誤判定しないよう、商品名の焙煎度表記を優先
        parsed["roast_level"] = explicit_roast
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    desc = detail["desc"]
    if desc:
        desc = re.sub(r"\s+", " ", desc)[:400]
    out = not detail["available"]
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
        "roast_selectable": False,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_list_items():
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    if not records:
        print("[warn] 商品0件のため出力しません")
        return
    with open("data_takanoniseko.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_takanoniseko.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
