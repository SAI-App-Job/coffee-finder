# -*- coding: utf-8 -*-
"""
scrape_timecoffee.py

待夢珈琲店(timecoffee.cafe、岐阜県瑞浪市一色町4丁目48-3、1977年開店の老舗珈琲専門店)の
珈琲豆の商品情報を取得する。WordPress + Welcart(usces)。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【robots.txtについて】
2026-10-11確認: User-agent: *に対し /wp-admin/ のみDisallow(admin-ajax.phpは許可)。
商品ページは制限対象外。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品一覧の取得方法について】
実データ確認済み(2026-10時点): 「一覧から選ぶ」ページ(/coffee_list/)に珈琲豆の全42商品が並ぶ
(焙煎度別カテゴリ /category/item/{light,medium,fullcity,dark}_roast/ は同じ商品が重複して載っている)。
そのうち「ブラジルCPC 2品種テイスティングセット」(セット商品)を除く41商品を対象とする。
アイス・ブレンド2種(プレミアム/ソフト)は豆(アイスコーヒー用ブレンド)のため採用する。
珈琲器具・ドリップスタンド・本は商品一覧に載らないため対象外。

【価格・重量について】
各商品ページには100g・200g・300g・400g・500gの重量別SKUが並ぶ(商品説明に「（単価）100g：650円」)。
最小重量(100g)のSKUの価格・在庫を代表とする。ホームページ価格は店頭価格とは異なる旨の注記あり。

【産地・焙煎度について】
商品ページの「産 地」欄(ブレンドは構成産地が並ぶためブレンドでは使わない)、
「ローストの度合い」欄(淡煎り/中煎り/中深煎り/深煎り等)から取得する。
説明文冒頭の赤字の入荷告知(「R8.10月～ 今年の豆が入荷いたしました！」)は除く。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "待夢珈琲店",
    "url": "https://timecoffee.cafe/",
    "platform": "WordPress(Welcart)",
    "address": "岐阜県瑞浪市一色町4丁目48-3",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-10確認。/wp-admin/のみDisallow。商品ページは制限対象外)",
}

BASE_URL = "https://timecoffee.cafe"
LIST_URL = f"{BASE_URL}/coffee_list/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 1
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップバッグ", "スタンド")
# 店の焙煎度欄の表記ゆれを統一する(「浅中煎り」=中浅煎り。「やや深」は商品説明が「中深煎りに焙煎」のため中深煎り)
ROAST_NORMALIZE = {"浅中煎り": "中浅煎り", "やや深": "中深煎り"}
SOLD_OUT_PATTERN = re.compile(r"売り?切れ|在庫なし|在庫切れ|SOLD ?OUT|入荷待ち|品切れ")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_item_urls() -> list[str]:
    html_text = fetch(LIST_URL)
    urls = re.findall(r'href="(https://timecoffee\.cafe/20\d\d/[^"]+)"', html_text)
    return list(dict.fromkeys(urls))


def th_value(soup: BeautifulSoup, label: str) -> str | None:
    for th in soup.find_all("th"):
        if re.sub(r"\s+", "", th.get_text()) == label:
            td = th.find_next_sibling("td")
            if td:
                return re.sub(r"\s+", " ", td.get_text(" ", strip=True)) or None
    return None


def parse_page(url: str) -> dict | None:
    soup = BeautifulSoup(fetch(url), "html.parser")
    name_el = soup.select_one("h2.item-name")
    if not name_el:
        return None
    name = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip()

    # 重量別SKU(最小重量を代表とする)
    skus = []
    for box in soup.select("div.skuform"):
        label = box.select_one("div.skuname")
        price_el = box.select_one("div.field_price")
        stock_el = box.select_one("div.zaikostatus")
        wm = re.search(r"(\d+)\s*g", label.get_text() if label else "")
        pm = re.search(r"[¥￥]\s*([\d,]+)", price_el.get_text() if price_el else "")
        if not (wm and pm):
            continue
        stock_text = stock_el.get_text(" ", strip=True) if stock_el else ""
        skus.append({
            "weight": int(wm.group(1)),
            "price": int(pm.group(1).replace(",", "")),
            "sold_out": bool(SOLD_OUT_PATTERN.search(stock_text)),
        })
    if not skus:
        return None
    rep = min(skus, key=lambda s: s["weight"])

    # 商品説明(赤字の入荷告知は除く)
    desc = None
    h4 = next((h for h in soup.find_all("h4", class_="h4_title") if "商品説明" in h.get_text()), None)
    if h4:
        box = h4.find_next_sibling("div")
        if box:
            for span in box.select("span"):
                if "red" in (span.get("style") or ""):
                    span.decompose()
            desc = re.sub(r"\s+", " ", box.get_text(" ", strip=True)).strip()
            # 「2023.11.23 入荷しました！」等の入荷告知は除く
            desc = re.sub(r"^\d{4}\.\d{1,2}\.\d{1,2}\s*入荷しました[！!]?\s*", "", desc)[:400] or None

    return {
        "url": url,
        "name": name,
        "origin_field": th_value(soup, "産地"),
        "roast_field": th_value(soup, "ローストの度合い"),
        "desc": desc,
        **rep,
    }


def build_record(info: dict) -> dict | None:
    name = info["name"]
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
        parsed["designated_brand"] = None
    else:
        field_country = detect_country_name(info["origin_field"] or "")
        if not parsed["origin_country"]:
            if field_country:
                parsed["origin_country"] = field_country
                parsed["origin_source"] = "description"
            else:
                d = detect_country_name(name)
                if d:
                    parsed["origin_country"] = d
                    parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST_NORMALIZE.get(info["roast_field"], info["roast_field"]) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": info["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": info["price"],
        "weight_g": info["weight"],
        "stock_status": "完売" if info["sold_out"] else "販売中",
        "out_of_stock": info["sold_out"],
        "product_url": info["url"],
    }


def scrape_all_products() -> list[dict]:
    records, seen = [], set()
    for url in list_item_urls():
        try:
            info = parse_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        time.sleep(DELAY)
        if info is None or info["name"] in seen:
            continue
        seen.add(info["name"])
        record = build_record(info)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_timecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_timecoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:25])


if __name__ == "__main__":
    main()
