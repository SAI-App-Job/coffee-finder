# -*- coding: utf-8 -*-
"""
scrape_baisenkaede.py

焙煎珈琲豆 楓(かえで)(大阪府吹田市古江台4丁目2-25 dios北千里5番館105号、阪急千里線北千里駅前。
公式 coffeekaede.com、Yahoo!ショッピング store.shopping.yahoo.co.jp/baisenkaede)の商品情報を取得する。
公式「当店はコーヒー豆をご注文都度、焙煎して販売しております」(注文ごとの受注焙煎)。

【プラットフォームについて】
店舗の商品一覧(/search.html、2ページ目以降は ?page=N)は Next.js の `__NEXT_DATA__` JSON に
商品名・価格・URLが埋め込まれている(scrape_frigoles.py と同型)。全158件(30件×5ページ+8件)。
実データ確認済み(2026-10-26)。

【対象商品について】
商品コード `mameNNN-<重量>.html` が重量違い(100g〜500g)で別ページに並ぶ。同一コードの
最小重量(ほぼ100g)のページを代表にする。除外: ドリップバッグ(drip001)、ナッツ(mame163/164)。
一覧タイトルに実重量と異なる表記(例: mame082-100 は「200g」表記)があるため、重量は URL の
末尾数字(=キャッチコピーの「100g」表記と一致)を採用する。

【重量・価格について】
店頭の説明に「焙煎後は生豆時の量目から10〜15%程度減少」とあり、表記重量は生豆重量。
価格は一覧JSONの `price`(税込)。焙煎度は購入時に選択式(「お好みの焙煎度」オプション)で
roast_selectable=True。説明文の「おすすめ」焙煎度を roast_hint に入れる。
在庫は商品ページの `item.stock.isAvailable` で判定する。
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
    "name": "焙煎珈琲豆 楓",
    "url": "https://store.shopping.yahoo.co.jp/baisenkaede/",
    "platform": "Yahoo!ショッピング",
    "address": "大阪府吹田市古江台4丁目2-25 dios北千里5番館105号",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。store.shopping.yahoo.co.jp/robots.txt は strcid/brandid/spec 等のクエリ付き検索のみ禁止。クエリなしの /search.html?page=N と商品ページを使用)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/baisenkaede/)の商品一覧と各商品ページを2026-10-26に取得。公式サイト(https://coffeekaede.com/)で所在地(北千里駅前のディオス5番館)、営業時間・店内でのお待ち可、「当店はコーヒー豆をご注文都度、焙煎して販売しております」を確認。公式お知らせ2026.10.08。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/baisenkaede"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 3.2
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
CODE_PATTERN = re.compile(r"/(mame\d+)-(\d+)\.html")

ORIGIN_OVERRIDES = {
    "ブルーマウンテン": "ジャマイカ",
    "エメラルドマウンテン": "コロンビア",
    "キリマンジャロ": "タンザニア",
    "トラジャ": "インドネシア",
    "マンデリン": "インドネシア",
    "ガラパゴス": "エクアドル",
    "モカシダモ": "エチオピア",
    "ガテマラ": "グアテマラ",
}
BLEND_KEYWORDS = ("ブレンド", "マイルドアイス")


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for page in range(0, 10):
        url = f"{BASE_URL}/search.html" + (f"?page={page}" if page else "")
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        results = m and json.loads(m.group(1))["props"]["initialState"]["bff"].get("searchResults")
        if not results:
            break
        n = 0
        for entries in results["items"].values():
            for entry in entries:
                content = entry.get("content") or {}
                if isinstance(content.get("items"), list):
                    for i in content["items"]:
                        if "name" in i:
                            items.append(i)
                            n += 1
        if n == 0:
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
        desc = BeautifulSoup(raw.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
    available, roast_selectable = True, False
    m = NEXT_DATA_PATTERN.search(text)
    if m:
        item = json.loads(m.group(1))["props"]["pageProps"].get("item") or {}
        available = bool((item.get("stock") or {}).get("isAvailable", True))
        roast_selectable = any("焙煎" in (o.get("name") or "") for o in item.get("selectOptionList") or [])
    return {"desc": desc, "available": available, "roast_selectable": roast_selectable}


def clean_name(title: str) -> str:
    name = unicodedata.normalize("NFKC", title)
    name = re.sub(r"^第\d+位\s*", "", name)
    name = re.sub(r"\s*(\d+)\s*[gG].*$", "", name)
    name = name.replace("コーヒー豆", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def roast_recommendation(desc: str | None) -> str | None:
    if not desc:
        return None
    m = re.search(r"おすすめ焙煎度\s*(\S+)", desc)
    if m:
        return m.group(1)
    m = re.search(r"([^\s、。]*ロースト)がおすすめ", desc)
    return m.group(1) if m else None


def pick_representatives(items: list[dict]) -> list[dict]:
    best: dict[str, tuple[int, dict]] = {}
    for item in items:
        m = CODE_PATTERN.search(item.get("url") or "")
        if not m:
            continue  # drip001 等(ドリップバッグ)
        code, weight = m.group(1), int(m.group(2))
        if code in ("mame163", "mame164"):  # ナッツ
            continue
        if code not in best or weight < best[code][0]:
            best[code] = (weight, item)
    return [dict(item, _weight=w) for w, item in best.values()]


def build_record(item: dict) -> dict:
    url = item["url"].split("?")[0]
    time.sleep(CRAWL_DELAY_SECONDS)
    detail = fetch_detail(url)
    name = clean_name(item["name"])
    desc = detail["desc"]
    parsed = parse_product(name)
    is_blend = any(k in name for k in BLEND_KEYWORDS)
    if is_blend:
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
        "roast_selectable": detail["roast_selectable"],
        "roast_hint": roast_recommendation(detail["desc"]),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": item["_weight"],
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    return [build_record(i) for i in pick_representatives(fetch_list_items())]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_baisenkaede.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisenkaede.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_hint"], r["roast_selectable"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
