# -*- coding: utf-8 -*-
"""
scrape_salviacoffee.py

サルビアコーヒー(珈琲館サルビア本店、千葉県館山市北条2576、salvia-coffee.com)の商品情報を取得する。
1971年創業のレストラン時代から自家焙煎を行う店舗で、店舗は本店のみ。WordPress + Welcart
(TABEI COFFEE と同じ構成)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(/coffee_beans)の一覧に、
ブレンド・深煎り・ストレート各種が200g/500gの別商品として並ぶ。同一銘柄は最小サイズ
(通常200g)のみを代表として採用する(500gは除外)。限定商品(パナマ・ゲイシャ50g、
ブルーマウンテンNo.1 100g、きまぐれセレクト150g、ラム樽熟成バレルエイジド100g)は
それぞれ単独サイズ。「アイスコーヒー(粉のみ)」は粉販売のため除外。
ドリップパック・ボトルアイス・カフェチョコ・陶器・セット・定期便は別カテゴリのため対象外。

【価格・重量・産地・在庫】
一覧ページの価格(税込)をそのまま採用。重量・原産国は各商品詳細ページの「【内容量】」「【原産国】」
から取得する。原産国が複数または「他」を含むもの(サルビアブレンド・深煎りコーヒー・
バレルエイジド)はブレンド扱いで産地None。在庫は詳細ページのWelcart隠しフィールド
(zaiko/zaikonum)から判定する(Welcartのカート処理と同じ条件)。
バレルエイジドコーヒーは商品名・内容量とも100gだが送料注記のみ「120g」とあり矛盾している。
名称・内容量の100gを採用した。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "サルビアコーヒー",
    "url": "https://salvia-coffee.com/",
    "platform": "WordPress + Welcart",
    "address": "千葉県館山市北条2576",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-10確認。/wp-admin/以外は制限なし)",
}

LIST_URL = "https://salvia-coffee.com/coffee_beans"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("粉のみ", "ドリップ", "セット", "定期便", "チョコ", "ボトル")
LIMITED_PREFIX = re.compile(r"^数量[\s　]*限定商品[\s　]*")
WEIGHT_SUFFIX = re.compile(r"[\s　]*(\d+)\s*[gｇ]\s*$")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    soup = fetch(LIST_URL)
    items = []
    for li in soup.select("li"):
        a = li.find("a", href=True)
        name_el = li.select_one("div.name")
        price_el = li.select_one("span.item_pr")
        if not (a and name_el and price_el):
            continue
        name = name_el.get_text(strip=True)
        pm = re.search(r"([\d,]+)", price_el.get_text())
        exp_el = li.select_one("div.exp")
        items.append({
            "name": name,
            "url": a["href"],
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "exp": exp_el.get_text(" ", strip=True) if exp_el else None,
        })
    return items


def base_name(name: str) -> str:
    n = LIMITED_PREFIX.sub("", name)
    n = WEIGHT_SUFFIX.sub("", n)
    return n.strip()


def parse_detail(url: str) -> dict:
    soup = fetch(url)
    text = soup.get_text("\n", strip=True)
    wm = re.search(r"【内容量】\s*(\d+)\s*[gｇ]", text)
    om = re.search(r"【原産国】\s*([^\n]+)", text)
    bm = re.search(r"【基本情報】\n((?:・[^\n]*\n?)+)", text)
    basic = bm.group(1).strip().replace("\n", " ") if bm else None
    zaiko = soup.find("input", id=re.compile(r"^zaiko\["))
    zaikonum = soup.find("input", id=re.compile(r"^zaikonum\["))
    out = False
    if zaiko is not None and zaikonum is not None:
        z = zaiko.get("value", "")
        n = zaikonum.get("value", "")
        out = z not in ("0", "1") or n == "0"
    return {
        "weight_g": int(wm.group(1)) if wm else None,
        "origin_text": om.group(1).strip() if om else None,
        "basic_info": basic,
        "out_of_stock": out,
    }


def build_record(item: dict, detail: dict) -> dict:
    name = LIMITED_PREFIX.sub("", item["name"]).strip()
    clean = WEIGHT_SUFFIX.sub("", name).strip()
    origin_text = detail["origin_text"] or ""
    basic = detail.get("basic_info") or ""
    multi = ("、" in origin_text) or ("他" in origin_text) or ("ブレンド" in name)

    parsed = parse_product(clean)
    if multi:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(origin_text)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "category_hint"
        parsed = apply_category_hint_fallback(parsed, origin_text)

    if not parsed["processing_method"]:
        parsed["processing_method"] = detect_processing_method(origin_text + " " + basic)

    weight = detail["weight_g"]
    if weight is None:
        wm = WEIGHT_SUFFIX.search(name)
        weight = int(wm.group(1)) if wm else None
    out = detail["out_of_stock"]
    roast = parsed["roast_level"]
    if "深煎り" in clean and not roast:
        roast = "深煎り"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": clean,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": item["exp"],
        "farm_note": basic or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    chosen: dict[str, dict] = {}
    order: list[str] = []
    for it in list_items():
        if any(k in it["name"] for k in EXCLUDE_KEYWORDS):
            continue
        key = base_name(it["name"])
        wm = WEIGHT_SUFFIX.search(LIMITED_PREFIX.sub("", it["name"]))
        w = int(wm.group(1)) if wm else 10**6
        if key not in chosen:
            order.append(key)
            chosen[key] = {**it, "_w": w}
        elif w < chosen[key]["_w"]:
            chosen[key] = {**it, "_w": w}

    records = []
    for key in order:
        it = chosen[key]
        try:
            detail = parse_detail(it["url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['url']} ({e})")
            continue
        records.append(build_record(it, detail))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_salviacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_salviacoffee.json に出力しました")


if __name__ == "__main__":
    main()
