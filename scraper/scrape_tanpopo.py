# -*- coding: utf-8 -*-
"""
scrape_tanpopo.py

珈専舎たんぽぽ(tanpopo.ocnk.net、〒654-2331 兵庫県神戸市西区神出町広谷608-4、自家焙煎珈琲、
運営はAnadacoffee Corporation)の商品情報を取得する。おちゃのこネット(UTF-8)。

【住所の確認(2026-10)】
サイト内「お店の紹介」ページ(/page/3)に「〒654-2331神戸市西区神出町広谷608-4」と記載。

【対象商品について】
実データ確認済み(2026-10時点): 「ブレンドコーヒー」(product-list/2)と「ストレートコーヒー」
(product-list/3)が対象。ブレンドは200g/500gが別商品(別pid)で並ぶため、同名の商品は最小重量
(200g)を代表とする。ストレートは200gのみ。冷珈琲(リキッド)・カフェオレベース・ドリップパック・
ギフト・コーヒー器具・チョコレート・グッズは除外。
商品名に重量が付いた形式(「たんぽぽブレンド200ｇ」)で、重量表記を除いたものを商品名とする。
価格は一覧の税込価格、在庫は一覧セルの`list_item_soldout`クラスで判定する。
詳細ページに産地・焙煎度・精製の構造化情報は無い(短い味わい説明のみ)ため、産地は商品名から判定する。
"""

import json
import re
import time
import unicodedata
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈専舎たんぽぽ",
    "url": "https://tanpopo.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "兵庫県神戸市西区神出町広谷608-4",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(おちゃのこネット標準構成)",
}

BASE_URL = "https://tanpopo.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# (カテゴリID, ブレンドか)
CATEGORIES = [(2, True), (3, False)]
WEIGHT_PATTERN = re.compile(r"\s*(\d+)\s*g\s*$", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ROAST_HINT_PATTERN = re.compile(r"(極深煎|中深煎|中浅煎|浅煎|中煎|深煎)り?")


def detect_roast_hint(desc: str | None) -> str | None:
    """説明文中の焙煎度表記(例:「深煎りブレンド」)を拾う。「深煎が多いマンデリンですが、
    当店では中煎にし」のように一般論と当店の仕様が並ぶ場合は「当店では」以降を優先する。"""
    if not desc:
        return None
    if "当店では" in desc:
        desc = desc.split("当店では", 1)[1]
    m = ROAST_HINT_PATTERN.search(desc)
    return (m.group(1) + "り") if m else None


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for cat, is_blend in CATEGORIES:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/product-list/{cat}"), "html.parser")
        for cell in soup.select("li.list_item_cell"):
            a = cell.select_one("a[href*='/product/']")
            pid_m = re.search(r"/product/(\d+)", a.get("href", "")) if a else None
            if not pid_m or pid_m.group(1) in seen:
                continue
            seen.add(pid_m.group(1))
            title = norm(cell.select_one(".goods_name").get_text(strip=True))
            wm = WEIGHT_PATTERN.search(title)
            if not wm:
                continue
            price_el = cell.select_one(".selling_price")
            pm = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            items.append({
                "pid": pid_m.group(1),
                "name": WEIGHT_PATTERN.sub("", title).strip(),
                "weight": int(wm.group(1)),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": "list_item_soldout" in " ".join(cell.get("class", [])),
                "is_blend": is_blend,
            })
        time.sleep(0.5)
    return items


def fetch_description(pid: str) -> str | None:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/product/{pid}"), "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    lines = [norm(l) for l in soup.get_text("\n", strip=True).split("\n")]
    lines = [l for l in lines if l]
    if "商品詳細" not in lines:
        return None
    start = lines.index("商品詳細") + 1
    end = next((i for i in range(start, len(lines)) if lines[i] in ("商品情報", "関連商品", "商品カテゴリ一覧")), len(lines))
    return " ".join(lines[start:end])[:300] or None


def build_record(it: dict) -> dict:
    name = it["name"]
    parsed = parse_product(name)
    if it["is_blend"]:
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    desc = fetch_description(it["pid"])
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
        "roast_hint": detect_roast_hint(desc),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/product/{it['pid']}",
    }


def scrape_all_products() -> list[dict]:
    groups = OrderedDict()
    for it in list_items():
        cur = groups.get(it["name"])
        if cur is None or it["weight"] < cur["weight"]:
            groups[it["name"]] = it
    records = []
    for it in groups.values():
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: pid={it['pid']} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tanpopo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tanpopo.json に出力しました")


if __name__ == "__main__":
    main()
