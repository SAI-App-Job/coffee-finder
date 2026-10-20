# -*- coding: utf-8 -*-
"""
scrape_randrcoffeelabo.py

R and R coffee labo(長崎県諫早市多良見町化屋、代表 西田憲生)の Yahoo!ショッピング店
(store.shopping.yahoo.co.jp/randrcoffeelabo)の商品情報を取得する。

【実店舗・自家焙煎の根拠(2026-10-20確認)】
 - 店の公式サイト(r.goope.jp/sr-42-423061s0083/): 店名「R and R coffee labo」、住所 諫早市多良見町化屋757-7、
   TEL 080-6433-3009、設備欄に「焙煎機」(店内に焙煎機)。食べログ・HAMONI・諫早グルメ・note(たらPAY)も 757-7。
 - ふるなび(furunavi.jp/product_detail.aspx?pid=592341): 「自家焙煎珈琲豆」「店主が…焙煎機でロースト」。
 - Yahoo!ショッピングの特商法ページは所在地が「化屋762-9」、連絡先が「化屋757-7」と不一致。
   実店舗(公式サイト・食べログ等)は一貫して757-7なので、757-7を採用した(762-9は他の第三者ページで確認できず)。

【対象商品について】
ショップカテゴリ「コーヒー豆」の全9件(すべて100g、豆のまま/粗挽き/中挽き/細挽きを選択)。
価格は商品ページの applicablePrice(税込)。焙煎度は商品説明の「Roast：」、精選は「生産処理：」の記載。
商品ページは `__NEXT_DATA__` JSON から取得する。
"""

import html
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_processing_method

SHOP_INFO = {
    "name": "R and R coffee labo",
    "url": "https://store.shopping.yahoo.co.jp/randrcoffeelabo/",
    "platform": "Yahoo!ショッピング",
    "address": "長崎県諫早市多良見町化屋757-7",
    "prefecture": "長崎県",
    "robots_txt_status": "未確認(Yahoo!ショッピングストアのrobots.txtは404。/search.htmlと各商品ページのみ使用)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/randrcoffeelabo/)の商品一覧・各商品ページを2026-10-20に確認。"
                   "住所は店の公式サイト(r.goope.jp)・食べログの757-7を採用(Yahoo!特商法の所在地欄は762-9で不一致)。"
                   "自家焙煎はふるなび返礼品の説明(店主が焙煎機でロースト)と公式サイトの設備欄(焙煎機)で確認",
    "last_verified_at": "2026-10-20",
}

STORE = "randrcoffeelabo"
LIST_URL = f"https://store.shopping.yahoo.co.jp/{STORE}/search.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 3
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
EXCLUDE_KEYWORDS = ("ドリップバッグ", "セット", "ギフト", "定期便", "生豆", "福袋")


def next_data(url):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
    return json.loads(m.group(1)) if m else None


def fetch_list_items():
    data = next_data(LIST_URL)
    groups = data["props"]["initialState"]["bff"]["searchResults"]["items"]
    items = {}
    for entries in groups.values():
        for entry in entries:
            content = entry.get("content") or {}
            if isinstance(content.get("items"), list):
                for i in content["items"]:
                    if "name" in i:
                        items[i["url"].split("?")[0]] = i
    return list(items.values())


def to_text(h):
    return BeautifulSoup(html.unescape(h or "").replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)


def build_record(item):
    title = unicodedata.normalize("NFKC", item["name"]).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    url = item["url"].split("?")[0]
    time.sleep(CRAWL_DELAY_SECONDS)
    pd = next_data(url)["props"]["pageProps"]["item"]
    info = to_text(pd.get("information"))
    caption = to_text(pd.get("caption"))
    available = bool((pd.get("stock") or {}).get("isAvailable", True))

    wm = re.search(r"(\d+)\s*[gG]\s*$", title)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"\s*\d+\s*[gG]\s*$", "", title).strip()

    rm = re.search(r"Roast\s*[:：]\s*(\S+)", info)
    roast = rm.group(1) if rm else None
    pm = re.search(r"生産処理\s*[:：]\s*(\S+)", info)
    processing = detect_processing_method(pm.group(1)) if pm else None

    parsed = parse_product(name)
    parsed = apply_category_hint_fallback(parsed, name)
    flavor = re.sub(r"\s+", " ", caption)[:400] if caption else None
    farm = info.replace("\n", " / ") if info else None

    out = not available
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": pd.get("applicablePrice"),
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    records = [r for r in (build_record(i) for i in fetch_list_items()) if r]
    with open("data_randrcoffeelabo.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_randrcoffeelabo.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
