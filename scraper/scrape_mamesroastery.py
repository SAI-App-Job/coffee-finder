# -*- coding: utf-8 -*-
"""
scrape_mamesroastery.py

マメーズ焙煎工房(mames.jp、東京都大田区蒲田1-18-5、運営:株式会社イマジンクラフト)の
商品情報を取得する。2006年創業のスペシャルティコーヒー専門の自家焙煎店(イタリア製
熱風式焙煎機を使用、焙煎後1週間を過ぎた豆は販売しない)。MakeShop(新形式 /view/item/)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(/view/category/0000000108、
全30件・1ページ)のうち、商品カテゴリ表示が「スペシャルティブレンド」「スペシャル
ティストレート」のものを対象とする。「お試しセット」(120g×4種・×2種)は複数銘柄の
セットのため除外。ドリップコーヒー・水出しコーヒー・カフェポッド・ギフト・器具・
オリーブオイル等は別カテゴリのため対象外。「水出しコーヒージャグ＆アイスブレンド
セット」はセット品のため除外。
「デカフェ(カフェインレス)メキシコ」はカフェインレス豆のためストレートとして対象。

【重量・価格・在庫】
商品詳細ページの「内容量」セレクトで最初に選択されている容量(ストレートは120g、
ブレンドは250g。いずれも最小サイズ)とその価格(一覧・詳細に表示される税込価格)を
採用する。在庫は一覧ページの「SOLD OUT」表示(p.item-soldout)で判定する。
ブレンドは配合国が複数のため産地None(「ブレンド内容」に国名の列挙はあるが
blend_componentsは空とする)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "マメーズ焙煎工房",
    "url": "https://www.mames.jp/",
    "platform": "MakeShop",
    "address": "東京都大田区蒲田1-18-5",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.mames.jp"
LIST_URL = f"{BASE_URL}/view/category/0000000108"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
TARGET_CATEGORIES = ("スペシャルティブレンド", "スペシャルティストレート")
NON_BEAN_KEYWORDS = ("セット", "福袋", "ジャグ", "ドリップ", "ポッド")
ROAST_PATTERN = re.compile(r"(中深煎り|浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_list(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    for li in soup.select("li"):
        name_a = li.select_one("p.item-name a")
        cat_el = li.select_one("p.item-category")
        price_el = li.select_one("p.price")
        if not (name_a and cat_el and price_el):
            continue
        m = re.search(r"/view/item/(\d+)", name_a["href"])
        pm = re.search(r"([\d,]+)", price_el.get_text())
        if not (m and pm):
            continue
        items.append({
            "id": m.group(1),
            "name": re.sub(r"\s+", " ", name_a.get_text(strip=True)).strip(),
            "category_label": cat_el.get_text(strip=True),
            "price": int(pm.group(1).replace(",", "")),
            "out_of_stock": li.select_one("p.item-soldout") is not None,
        })
    return items


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    weight_g = None
    sel = soup.select_one('select[data-id="makeshop-item-option1"]')
    if sel:
        opt = sel.select_one("option[selected]")
        if opt is None:
            opt = next((o for o in sel.select("option") if o.get("value") not in (None, "", "0")), None)
        if opt:
            wm = re.search(r"(\d+)\s*g", opt.get_text())
            if wm:
                weight_g = int(wm.group(1))
    paragraphs: list[str] = []
    # 説明文は「この商品について問い合わせる」の直後から「システム商品コード」の手前まで
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    if "この商品について問い合わせる" in lines:
        start = lines.index("この商品について問い合わせる") + 1
        end = next((i for i in range(start, len(lines)) if lines[i] == "システム商品コード"), len(lines))
        paragraphs = lines[start:end]
    if weight_g is None:
        # 完売品はセレクトが出力されないため、本文の「内容量」行(例:「250g・500g」)の最小値を採用
        all_lines = lines
        for i, ln in enumerate(all_lines[:-1]):
            if ln == "内容量" and re.search(r"\d+\s*g", all_lines[i + 1]):
                weights = [int(x) for x in re.findall(r"(\d+)\s*g", all_lines[i + 1])]
                weight_g = min(weights)
                break
    return {"weight_g": weight_g, "paragraphs": paragraphs}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if item["category_label"] not in TARGET_CATEGORIES:
        return None
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    display = re.sub(r"^【[^】]*】", "", name).strip()
    parsed = parse_product(display)
    if item["category_label"] == "スペシャルティブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート" if parsed["category"] != "フレーバー" else parsed["category"]
        parsed = apply_category_hint_fallback(parsed, display)

    paragraphs = detail["paragraphs"]
    flavor_notes = next((p[:300] for p in paragraphs if len(p) >= 25 and not p.startswith(("【", "＜", "<"))), None)
    farm_bits = []
    for ln in paragraphs:
        m = re.match(r"^【(生産者|農園名|産地|標高|品種|精製|生産国)】\s*(.+)$", ln)
        if m:
            farm_bits.append(f"{m.group(1)}:{m.group(2).strip()}")
    farm_note = " / ".join(farm_bits) or None
    if parsed["processing_method"] is None:
        for b in farm_bits:
            if b.startswith("精製:"):
                from coffee_parser import detect_processing_method
                parsed["processing_method"] = detect_processing_method(b)
    rm = ROAST_PATTERN.search(" ".join(paragraphs))

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
        "roast_hint": rm.group(1) if rm else None,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if item["out_of_stock"] else "販売中",
        "out_of_stock": item["out_of_stock"],
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list(fetch(LIST_URL)):
        if item["category_label"] not in TARGET_CATEGORIES or any(k in item["name"] for k in NON_BEAN_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/view/item/{item['id']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            detail = {"weight_g": None, "paragraphs": []}
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamesroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamesroastery.json に出力しました")


if __name__ == "__main__":
    main()
