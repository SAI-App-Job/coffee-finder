# -*- coding: utf-8 -*-
"""
scrape_misakiroastery.py

岬の焙煎所(https://live-coffee.ocnk.net/、兵庫県神戸市兵庫区和田宮通3-2-22、運営: 株式会社ライブコーヒー)の商品情報を取得する。おちゃのこネット(Ocnk)。

【対象商品について】
実データ確認済み(2026-10時点): 「ストレートコーヒー」(product-list/1)と「ブレンドコーヒー」(product-list/3)のカテゴリ。
同一銘柄が100g/500gの別商品で並ぶため、最小の100gを代表とする(ストレート7銘柄+ブレンド5銘柄)。
ブレンド3種セット・ドリップバッグ・キッズコーヒー等は対象外(カテゴリ17・6は取得しない)。
価格は一覧ページの税込販売価格、在庫は一覧の品切れ表示(list_item_soldout)と商品ページの「カートに入れる」有無で判定する。
焙煎度・ブレンド構成国・説明は商品ページの説明文(div.item_desc_text)から取得する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "岬の焙煎所",
    "url": "https://live-coffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "兵庫県神戸市兵庫区和田宮通3-2-22",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-10-26確認。robots.txtはGPTBot・Bytespider等の特定クローラのみ全面禁止で、それ以外は制限なし。識別可能なUser-Agentを使用)",
    "source_note": "販売先 https://live-coffee.ocnk.net/ のカテゴリ(product-list/1・3)と各商品ページ、特商法ページ(/info/law)・ご利用案内を2026-10-26に確認。お知らせ最新は2026-10-21。実店舗(焙煎所での豆販売・テイクアウト、併設カフェ)あり",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://live-coffee.ocnk.net"
CATEGORIES = [("1", "single"), ("3", "blend")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2
MAX_PAGES = 10
ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
NAME_WEIGHT = re.compile(r"\s*(\d+)\s*[gｇ]\s*$")
SEASON_PREFIX = re.compile(r"^\d+月のスペシャルティコーヒー\s*")


def fetch_html(url: str) -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/product-list/{cat_id}" + ("" if page == 1 else f"?page={page}")
            soup = BeautifulSoup(fetch_html(url), "html.parser")
            new = 0
            for cell in soup.select("li.list_item_cell"):
                a = cell.select_one("a.list_item_link")
                name_el = cell.select_one(".goods_name")
                if not (a and name_el):
                    continue
                m = re.search(r"/product/(\d+)", a["href"])
                if not m or m.group(1) in items:
                    continue
                new += 1
                price_el = cell.select_one(".selling_price .figure")
                pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
                items[m.group(1)] = {
                    "pid": m.group(1),
                    "name": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name_el.get_text(" ", strip=True))).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "sold_out": "list_item_soldout" in cell.get("class", []),
                    "group": group,
                }
            if new == 0:
                break
    return list(items.values())


def fetch_detail(pid: str) -> tuple[str | None, bool]:
    """商品ページの説明文(整形済み)と、カートボタンの有無(購入可能か)を返す。"""
    html_text = fetch_html(f"{BASE_URL}/product/{pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    el = soup.select_one("div.item_desc_text")
    text = el.get_text("\n", strip=True) if el else None
    purchasable = "カートに入れる" in html_text
    return text, purchasable


def main():
    best: dict[str, tuple[int, dict]] = {}
    for item in list_items():
        m = NAME_WEIGHT.search(item["name"])
        if not m or item["price"] is None:
            continue  # 「ブレンド3種セット」など重量表記のない商品は対象外
        weight = int(m.group(1))
        base = SEASON_PREFIX.sub("", NAME_WEIGHT.sub("", item["name"])).strip()
        key = (item["group"], base)
        cur = best.get(key)
        if cur is None or weight < cur[0]:
            best[key] = (weight, item | {"base": base})

    records = []
    for (group, base), (weight, item) in best.items():
        text, purchasable = fetch_detail(item["pid"])
        desc = None
        if text:
            lines = [l for l in text.split("\n") if l.strip() and not l.startswith("☆")]
            desc = re.sub(r"\s+", " ", " ".join(lines))[:400] or None
        parsed = parse_product(base)
        blend_components = []
        if group == "blend":
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            cm = re.search(r"ブレンド内容[:：]\s*([^\n]+)", text or "")
            if cm:
                for part in re.split(r"[・、,/]", cm.group(1)):
                    c = detect_country_name(part)
                    if c and {"origin_country": c} not in blend_components:
                        blend_components.append({"origin_country": c})
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(base)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, base)
        if not parsed["processing_method"] and text:
            parsed["processing_method"] = extract_from_description(text)["processing_method"]

        rm = ROAST_PATTERN.search(base)
        if not rm and text:
            rm = re.search(r"焙煎度合?[:：]\s*(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)", text)
        roast_level = rm.group(1) if rm else None

        sold_out = item["sold_out"] or not purchasable
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_level,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
            "price": item["price"],
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })

    output = {"shop": SHOP_INFO, "products": records}
    with open("data_misakiroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_misakiroastery.json に出力しました")


if __name__ == "__main__":
    main()
