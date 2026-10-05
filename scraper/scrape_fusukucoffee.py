# -*- coding: utf-8 -*-
"""
scrape_fusukucoffee.py

フスクコーヒー(FusukuCoffee、福岡県福岡市中央区谷1-14-2 裏六本松ビルヂング2F、公式 fusukucoffee.jp)の
商品情報を取得する。オンラインショップは fusuku.shop-pro.jp(カラーミーショップ、EUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「産地で選ぶコーヒー豆」(cbid=2878205)、
「趣味から生まれたブレンドコーヒー」(2882541)、「フードペアリングのブレンドコーヒー」(2882542)、
「その他気分で飲みたいブレンドコーヒー」(2882543)の計約22商品(全て100g)を対象とする。
同一豆で焙煎度違い(中煎り/深煎り)の商品は別商品として扱う。
次は対象外: 水出しコーヒーパック、ドリップバッグ、クール便指定。

【価格・重量・在庫】
重量・焙煎度は商品名(「100g」「中煎り」等)から取得。価格は商品ページの
`var Colorme`内の sales_price_including_tax(税込。店頭表示は「756円(本体700円、税56円)」)。
在庫はinventory_control=noneで構造化されていないため、商品ページに「ADD TO CART」があるか、
「SOLD OUT」表記が無いかで判定する。商品ページに説明文は無く、産地・精製方法・焙煎度は商品名のみ
から取得するため、flavor_notesはnull。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "フスクコーヒー",
    "url": "https://fusukucoffee.jp/",
    "platform": "カラーミーショップ",
    "address": "福岡県福岡市中央区谷1-14-2 裏六本松ビルヂング2F",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://fusuku.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
STRAIGHT_CATEGORY = "2878205"
BLEND_CATEGORIES = ["2882541", "2882542", "2882543"]
MAX_PAGES = 5
EXCLUDE_KEYWORDS = ("水出し", "ドリップバッグ", "クール便", "セット", "ギフト")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def collect_ids(cbid: str) -> list[str]:
    ids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        soup = BeautifulSoup(fetch_html(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0&page={page}"), "html.parser")
        new = []
        for a in soup.select("a[href*='?pid=']"):
            m = re.search(r"pid=(\d+)", a["href"])
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
                new.append(m.group(1))
        if not new:
            break
    return ids


def parse_item(pid: str, is_blend_category: bool) -> dict | None:
    url = f"{BASE_URL}/?pid={pid}"
    html = fetch_html(url)
    m = re.search(r"var Colorme\s*=\s*(\{.*?\});\s*\n", html, re.S)
    if not m:
        return None
    prod = json.loads(m.group(1)).get("product") or {}
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", prod.get("name") or "")).strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    price = prod.get("sales_price_including_tax")
    wm = WEIGHT_PATTERN.search(title)
    if price is None or not wm:
        return None
    weight = int(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)

    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = soup.get_text("\n", strip=True)
    out_of_stock = ("ADD TO CART" not in text) or bool(re.search(r"SOLD\s*OUT|売り切れ|在庫切れ", text, re.I))

    parsed = parse_product(title)
    if is_blend_category or "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    rm = COARSE_ROAST_PATTERN.search(title)
    roast_level = rm.group(1) if rm else parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price),
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    targets: dict[str, bool] = {}
    for pid in collect_ids(STRAIGHT_CATEGORY):
        targets.setdefault(pid, False)
    for cb in BLEND_CATEGORIES:
        for pid in collect_ids(cb):
            targets[pid] = True
    records = []
    for pid, is_blend in targets.items():
        rec = parse_item(pid, is_blend)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_fusukucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fusukucoffee.json に出力しました")


if __name__ == "__main__":
    main()
