# -*- coding: utf-8 -*-
"""
scrape_ranacoffee.py

RANACOFFEE(公式 https://www.ranacoffee.com/、ストア https://beans-store.ranacoffee.com/、
香川県高松市牟礼町牟礼2421-13)の商品情報を取得する。FC2ショッピングカート(独自ドメイン)。

【対象商品について】
実データ確認済み(2026-10-15): カテゴリ ca=4「ブレンドコーヒー」(3商品)と ca=5「シングル
オリジンコーヒー」(9商品中、セレクションSET 2PAC/4PACの2商品を除く7商品)が対象。
ca=6 コーヒー器具(8点)、ca=8 ギフト(2点)は対象外。全て200g単品(商品名末尾に重量)。
バリエーションは挽き方のみで価格は同一。商品ページに焙煎度の記載は無いためnull。
産地は本文の「国:」欄、精製は「生産処理:」欄から取得する(商品名の産地表記が本文と食い違う
商品があるため。例: 「グアテマラ エルインヘルト タンザニア カトゥアイ」は本文でグアテマラ産)。
在庫は variation の option の data-stock / data-submit で判定する(全件在庫5または3)。
特商法(/laws)の販売業者はRANACOFFEE、所在地は香川県高松市牟礼町牟礼2421-13。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "RANACOFFEE",
    "url": "https://www.ranacoffee.com/",
    "platform": "FC2ショッピングカート(独自ドメイン beans-store.ranacoffee.com)",
    "address": "香川県高松市牟礼町牟礼2421-13",
    "prefecture": "香川県",
    "robots_txt_status": "実質許可(2026-10確認。/cancel/・/setup/・/tools/のみDisallow)",
}

BASE_URL = "https://beans-store.ranacoffee.com"
CATEGORIES = [(4, "ブレンド"), (5, "シングル")]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_NAME_KEYWORDS = ["SET", "セット", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\s*$", re.I)
PRICE_PATTERN = re.compile(r"[￥¥]\s*([\d,]+)")
FIELD_PATTERN = re.compile(r"(国|生産処理)\s*[:：]\s*([^\s]+)")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_items() -> list[tuple[str, str, str]]:
    """(商品URL, 一覧上の商品名, カテゴリ) を返す。"""
    items = []
    seen = set()
    for ca, label in CATEGORIES:
        soup = BeautifulSoup(fetch_html(f"{BASE_URL}/?ca={ca}"), "html.parser")
        time.sleep(CRAWL_DELAY_SECONDS)
        for li in soup.select("li.itemlist_main_card_item"):
            a = li.find("a")
            name_el = li.select_one(".itemlist_main_cardItem_detail_name")
            if not a or not name_el:
                continue
            name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name_el.get_text(strip=True)))
            m = re.match(r"/ca(\d+)/(\d+)/", a["href"])
            if not m or m.group(2) in seen:
                continue
            if any(k in name for k in EXCLUDE_NAME_KEYWORDS):
                continue
            seen.add(m.group(2))
            items.append((f"{BASE_URL}/ca{m.group(1)}/{m.group(2)}/p-r-s/", name, label))
    return items


def build_record(url: str, list_name: str, label: str) -> dict | None:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    options = [o for o in soup.select("select option[data-stock]")]
    sold_out = bool(options) and all(o.get("data-stock") == "0" or o.get("data-submit") == "0" for o in options)

    for sc in soup(["script", "style"]):
        sc.decompose()
    text = soup.get_text("\n", strip=True)
    flat = re.sub(r"\s+", " ", text)

    wm = WEIGHT_PATTERN.search(list_name)
    weight = int(wm.group(1)) if wm else None
    name = WEIGHT_PATTERN.sub("", list_name).strip()

    price = None
    pm = PRICE_PATTERN.search(text)
    if pm:
        price = int(pm.group(1).replace(",", ""))

    # 本文: 「お知らせメールを申し込む」の注意書きの後〜「カテゴリ」の前
    desc = None
    i = text.find("ご購入は先着順と致します。")
    j = text.find("\nカテゴリ\n", i if i >= 0 else 0)
    if i >= 0 and j > i:
        desc = re.sub(r"\s+", " ", text[i + len("ご購入は先着順と致します。"):j]).strip()[:400] or None

    fields = {k: v for k, v in FIELD_PATTERN.findall(flat)}

    parsed = parse_product(name)
    if label == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        country = fields.get("国")
        if country:
            parsed["origin_country"] = detect_country_name(country) or country
            parsed["origin_source"] = "description"
        else:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        raw_pm = fields.get("生産処理")
        if raw_pm:
            parsed["processing_method"] = normalize_processing_method(raw_pm)

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
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url, name, label in collect_items():
        try:
            rec = build_record(url, name, label)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {url} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ranacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ranacoffee.json に出力しました")


if __name__ == "__main__":
    main()
