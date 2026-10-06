# -*- coding: utf-8 -*-
"""
scrape_hiroshimacoffee.py

広島珈琲(コスモステージ有限会社、広島県広島市安芸区矢野東5丁目2-24、
Yahoo!ショッピング store.shopping.yahoo.co.jp/hiroshimacoffee、楽天にも同名店 item.rakuten.co.jp/hiroshimacoffee)
の商品情報を取得する。

【プラットフォームについて】
Yahoo!ショッピングストア。店舗カテゴリ「自家焙煎コーヒー豆」(bcabb2c8df.html、実データ確認済み
2026-10-06: 69件、全262件のうち)の一覧は Next.js の `__NEXT_DATA__` JSON に商品名・価格・URLが
埋め込まれている(1ページ30件、2ページ目以降は ?page=1, ?page=2)。カテゴリは焙煎豆のみ
(ドリップバッグ・セット・アイスコーヒー・器具・菓子などは別カテゴリのため最初から含まれない)。

【対象商品・代表1件について】
同一銘柄が100g/200g/500g/1kg の重量違いで別商品ページになっているため、銘柄(タイトルの「」内)ごとに
最小重量の商品を代表1件として採用する(重複掲載で同重量が複数ある場合は先に出現した方)。
在庫は商品ページの `item.stock.isAvailable` で判定。
"""

import html
import json
import re
import time
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "広島珈琲",
    "url": "https://store.shopping.yahoo.co.jp/hiroshimacoffee/",
    "platform": "Yahoo!ショッピング",
    "address": "広島県広島市安芸区矢野東5丁目2-24",
    "prefecture": "広島県",
    "robots_txt_status": "未確認(Yahoo!ショッピングストアのrobots.txtは404。カテゴリ一覧と商品ページのみ使用)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/hiroshimacoffee"
CATEGORY_URL = f"{BASE_URL}/bcabb2c8df.html"
LIST_URLS = [CATEGORY_URL, CATEGORY_URL + "?page=1", CATEGORY_URL + "?page=2"]
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# 国名がタイトルから自動判定できない銘柄の補完(商品説明・銘柄の一般的な産地による)
ORIGIN_OVERRIDES = {
    "ホワイトキャメル": "イエメン",
    "モカ・シダモ": "エチオピア",
    "アンティグア": "グアテマラ",
    "トラジャ": "インドネシア",
    "マンデリン": "インドネシア",
    "ブルーマウンテン": "ジャマイカ",
    "ハイマウンテン": "ジャマイカ",
    "キリマンジャロ": "タンザニア",
}


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for url in LIST_URLS:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        if not m:
            continue
        data = json.loads(m.group(1))
        groups = data["props"]["initialState"]["bff"]["searchResults"]["items"]
        for entries in groups.values():
            for entry in entries:
                content = entry.get("content") or {}
                if isinstance(content.get("items"), list):
                    items.extend(i for i in content["items"] if "name" in i)
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
        desc = BeautifulSoup(raw.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
    available = True
    m = NEXT_DATA_PATTERN.search(text)
    if m:
        item = json.loads(m.group(1))["props"]["pageProps"].get("item") or {}
        available = bool((item.get("stock") or {}).get("isAvailable", True))
    return {"desc": desc, "available": available}


def parse_weight(title: str) -> int | None:
    t = unicodedata.normalize("NFKC", title)
    # 「500g(250g×2)」のように先頭の重量を採用
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", t, re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    return int(round(v * 1000)) if m.group(2).lower() == "kg" else int(v)


def brand_of(title: str) -> str:
    """タイトルから銘柄名を取り出す(「」内。モカ・天空のホワイトキャメル等は接頭語を補う)。"""
    t = unicodedata.normalize("NFKC", title)
    t = t.replace("自家焙煎コーヒー", "自家焙煎コーヒー ")
    m = re.search(r"「([^」]+)」", t)
    if not m:
        # 「」が無い銘柄(自家焙煎ドミニカブレンド 200g)
        m2 = re.search(r"自家焙煎\s*(\S+?)\s*\d", t)
        return m2.group(1) if m2 else t
    name = m.group(1)
    if name == "グルメ":
        m = re.findall(r"「([^」]+)」", t)
        name = m[1] if len(m) > 1 else name
    if "ホワイトキャメル" in name:
        name = "モカ 天空のホワイトキャメル"
    if "カリブ海" in t and name == "ドミニカ":
        name = "ドミニカ(カリブ海のコーヒー)"
    if "モカマタリ" in name:
        name = "モカマタリ NO9"
    return name


def pick_representatives(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in items:
        title = it["name"]
        key = brand_of(title)
        it["_brand"] = key
        it["_weight"] = parse_weight(title)
        groups.setdefault(key, []).append(it)
    reps = []
    for key, lst in groups.items():
        known = [i for i in lst if i["_weight"]]
        reps.append(min(known, key=lambda i: i["_weight"]) if known else lst[0])
    return reps


def build_record(item: dict) -> dict:
    url = (item.get("url") or "").split("?")[0]
    time.sleep(CRAWL_DELAY_SECONDS)
    detail = fetch_detail(url)
    name = item["_brand"]
    weight = item["_weight"]

    parsed = parse_product(name)
    if "ブレンド" in name or "アンティグアの恋人" in name:  # 恋人は商品説明に「他2種類をブレンド」とある
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if k in name), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if "コナ" in name:
            parsed["origin_country"] = "アメリカ(ハワイ)"
            parsed["origin_source"] = "raw_name"

    # 焙煎度はタイトルに「浅煎り」とある銘柄のみ採用(「ハイマウンテン」を「ハイロースト」と誤検出するため
    # parse_productの結果は使わない)。それ以外は不明として None
    roast = "浅煎り" if name.startswith("浅煎り") else None

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
        "roast_level": roast,
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
    items = fetch_list_items()
    print(f"[list] カテゴリ一覧 {len(items)}件")
    reps = pick_representatives(items)
    return [build_record(i) for i in reps]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hiroshimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hiroshimacoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
