# -*- coding: utf-8 -*-
"""
scrape_potacupofcoffee.py

POT A CUP OF COFFEE(鹿児島県鹿屋市東原町2848-3、雑貨店 Araheam と共通の
カラーミーショップ https://store.araheam.com/)の自家焙煎コーヒー豆の商品情報を取得する。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

robots.txt確認済み(2026-10): /secure/ と /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
Araheam 共通ショップのうち、カテゴリ「POT A CUP OF COFFEE」(cbid=2844463)の一覧のみを対象に
する(雑貨・菓子・ドリッパーなど Araheam 側の商品は含めない)。
ドリップバッグ・SET・ドリッパー・クッキー・シロップ・テリーヌは除外し、
商品名に「200g」と「Roast」を含む豆の商品だけを対象とする。

【価格・重量・産地・焙煎度】
価格は税込表示(購入時に豆のまま/中挽き/粗挽きを選ぶが同額)。重量は商品名の「200g」。
焙煎度は商品名の「【Light Roast】」「【Dark Roast】」から。
商品説明の [テイスト]・[国]・[エリア]・[標高]・[品種]・[生産処理] から産地等を取る。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "POT A CUP OF COFFEE",
    "url": "https://store.araheam.com/",
    "platform": "カラーミーショップ(shop-pro.jp、雑貨店 Araheam と共通)",
    "address": "鹿児島県鹿屋市東原町2848-3",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://store.araheam.com/"
CATEGORY_URL = BASE_URL + "?mode=cate&cbid=2844463&csid=0"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["Drip Bag", "ドリップバッグ", "SET", "DRIPPER", "クッキー", "syrup", "テリーヌ"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\b", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"[【\[]\s*([A-Za-z ]*Roast)\s*[】\]]", re.IGNORECASE)
ROAST_MAP = {
    # Dark Roast は標準の8段階のどれに当たるか不明のため、roast_level は None で roast_hint のみ保持
    "light roast": "ライトロースト", "medium roast": "ミディアムロースト",
}


def fetch_page(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup, text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 6):
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}&page={page}"
        soup, _ = fetch_page(url)
        found = 0
        for a in soup.find_all("a", href=re.compile(r"[?&]pid=\d+")):
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            name = clean(a.get_text())
            if not name:
                continue
            found += 1
            seen.add(m.group(1))
            box = a.find_parent(["li", "div"], class_=re.compile("item|prd|product"))
            box_text = box.get_text(" ") if box else ""
            if any(k.lower() in name.lower() for k in NON_BEAN_KEYWORDS):
                continue
            if not WEIGHT_PATTERN.search(name) or "roast" not in name.lower():
                continue
            items.append({"pid": m.group(1), "list_name": name, "url": f"{BASE_URL}?pid={m.group(1)}",
                          "sold_out": bool(re.search(r"SOLD ?OUT", box_text, re.IGNORECASE))})
        time.sleep(CRAWL_DELAY_SECONDS)
        if not found:
            break
    return items


def parse_detail(item: dict) -> dict | None:
    soup, text = fetch_page(item["url"])
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product")
    if not product:
        return None
    name = clean(product.get("name"))
    prices = [v.get("option_price_including_tax") for v in (product.get("variants") or [])
              if v.get("option_price_including_tax")]
    price = min(prices) if prices else product.get("sales_price_including_tax")

    form = soup.select_one("form[name=product_form]")
    body = form.get_text("\n") if form else ""
    body = re.sub(r"[ \t　]+\n", "\n", body)

    def field(key):
        mm = re.search(r"\[" + key + r"\]\s*\n\s*([^\n\[]+)", body)
        return clean(mm.group(1)) if mm else None

    wm = WEIGHT_PATTERN.search(name)
    rm = ROAST_PATTERN.search(name)
    return {
        "name": name, "price": price, "weight": int(wm.group(1)) if wm else None,
        "url": item["url"], "sold_out": item["sold_out"], "stock_num": product.get("stock_num"),
        "roast_text": rm.group(1).strip() if rm else None,
        "taste": field("テイスト"), "country": field("国"), "area": field("エリア"),
        "elevation": field("標高"), "variety": field("品種"), "process": field("生産処理"),
    }


def build_record(d: dict) -> dict | None:
    # 商品名から重量・焙煎度の表記を除く: "Kenya Gatura AB 200g【Light Roast】" → "Kenya Gatura AB"
    name = clean(ROAST_PATTERN.sub("", re.sub(r"\s*\d+\s*g\b", "", d["name"], flags=re.IGNORECASE)))
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    parsed["category"] = "ストレート"
    country = detect_country_name(d["country"]) if d["country"] else None
    if country:
        parsed["origin_country"] = country
        parsed["origin_source"] = "product_description"
    elif not parsed["origin_country"]:
        c = detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
    if d["process"]:
        pm = normalize_processing_method(d["process"])
        if pm:
            parsed["processing_method"] = pm
    parsed = apply_category_hint_fallback(parsed, name)
    roast_level = ROAST_MAP.get((d["roast_text"] or "").lower())
    farm_parts = []
    if d.get("area"):
        farm_parts.append(f"エリア: {d['area']}")
    if d.get("elevation"):
        farm_parts.append(f"標高: {d['elevation']}")
    if d.get("variety"):
        farm_parts.append(f"品種: {d['variety']}")
    out = d["sold_out"] or (isinstance(d.get("stock_num"), int) and d["stock_num"] <= 0)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": d["roast_text"],
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": d["taste"],
        "blend_components": [],
        "decaf_process": None,
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": bool(out),
        "product_url": d["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in scrape_list():
        try:
            d = parse_detail(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if not d:
            continue
        rec = build_record(d)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_potacupofcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_potacupofcoffee.json に出力しました")


if __name__ == "__main__":
    main()
