# -*- coding: utf-8 -*-
"""
scrape_arovor.py

コーヒービーンズショップ アロバー(arovor.com、香川県高松市国分寺町新名1225-5 国分寺店<本店>)の
商品情報を取得する。ショップサーブ(ShopServe、UTF-8)。

【店舗・住所について】
実データ確認済み(2026-10-15): 店舗は国分寺店(高松市国分寺町新名1225-5、本店)と松縄店(高松市松縄町
1112-16)の2店舗。株式会社アロバーの本社所在地・特定商取引法表記の所在地とも国分寺店の住所。
公式サイト(店舗案内・会社概要・FAQ・商品ページ)に「どちらの店舗で焙煎しているか」の記載は見つからなかった
ため、本店である国分寺店の住所を採用する。

【対象商品】
実データ確認済み: 「コーヒー豆」カテゴリ(/SHOP/182166/list.html、ページネーションなし)に9銘柄が
100g・200gの別商品ページとして並ぶ(計18件、サブカテゴリは全て同一商品の再分類)。同一銘柄の200gは
大容量違いとして除外し、100gを代表に収録する。ブレンド3(arovor blend=35周年限定、潤-JUN-、
ジェヌイーノ)・季節限定ブレンド1(時を編む、9月限定)・シングル農園5。
商品ページの「商品詳細」から産地・標高・品種・精製方法・焙煎度合いを取る。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (apply_category_hint_fallback, detect_country_name,
                           detect_stock_status, normalize_processing_method, parse_product)

SHOP_INFO = {
    "name": "コーヒービーンズショップ アロバー",
    "url": "https://arovor.com/",
    "platform": "ショップサーブ",
    "address": "香川県高松市国分寺町新名1225-5",
    "prefecture": "香川県",
    "robots_txt_status": "未確認(robots.txtは404)",
}

BASE_URL = "https://arovor.com"
LIST_URL = f"{BASE_URL}/SHOP/182166/list.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5
SPEC_LABELS = ("農園名", "農園主", "産地", "標高", "品種", "精製方法", "処理方法", "風味特性",
               "焙煎度合い", "焙煎度合", "原産国", "ブレンド方法")
NOTE_STOPS = ("※", "商品詳細", "焙煎へのこだわり", "■", "こんな", "珈琲のそばには", "インターネット", "珈琲データ")
BLEND_OVERRIDES = ("時を編む", "arovor blend")


def fetch(url: str) -> BeautifulSoup:
    for attempt in range(5):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code in (429, 502, 503, 504) and attempt < 4:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        break
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def norm_title(t: str) -> str:
    t = re.sub(r"\s+", " ", t.replace("ｇ", "g").replace("　", " ")).strip()
    return t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def split_weight(title: str) -> tuple[str, int | None]:
    t = norm_title(title)
    m = re.search(r"(\d+)\s*g\s*$", t)
    weight = int(m.group(1)) if m else None
    return (t[:m.start()].strip() if m else t), weight


def list_items() -> list[dict]:
    soup = fetch(LIST_URL)
    items = []
    for sec in soup.select("section.column4"):
        a = sec.select_one("h2 a")
        if not a:
            continue
        price_el = sec.select_one(".selling_price")
        price_m = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        base, weight = split_weight(a.get_text(strip=True))
        items.append({
            "title": a.get_text(strip=True),
            "base": base,
            "weight_g": weight,
            "path": a["href"],
            "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        })
    return items


def detail(path: str) -> dict:
    soup = fetch(BASE_URL + path)
    for t in soup(["script", "style"]):
        t.decompose()
    box = soup.select_one("#main-column")
    lines = [ln.strip() for ln in box.get_text("\n", strip=True).split("\n") if ln.strip()]
    spec = {}
    for i, ln in enumerate(lines[:-1]):
        key = re.sub(r"\s+", "", ln)   # 「産　地」「標　高」等の全角空白入りラベルを正規化
        if key in SPEC_LABELS and key not in spec:
            spec[key] = lines[i + 1]
    if "処理方法" in spec and "精製方法" not in spec:
        spec["精製方法"] = spec["処理方法"]
    notes = []
    for marker in ("味わいの特徴", "■ 味の特徴"):
        if marker in lines:
            for ln in lines[lines.index(marker) + 1:]:
                if ln.startswith(NOTE_STOPS) or len(notes) >= 3:
                    break
                notes.append(ln)
            break
    # 在庫: 「在庫」見出し以降の「在庫あり」が1つでもあれば販売中
    stock_part = lines[lines.index("在庫"):lines.index("在庫") + 8] if "在庫" in lines else []
    in_stock = any(ln == "在庫あり" for ln in stock_part)
    sold_out = (not in_stock) and any(re.search(r"在庫なし|売り切れ|品切れ|SOLD", ln) for ln in stock_part)
    if spec.get("風味特性"):
        notes.append("風味特性：" + spec["風味特性"])
    return {"spec": spec, "notes": " ".join(notes) or None, "sold_out": sold_out}


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = list_items()
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["base"], []).append(it)
    records, excluded = [], []
    for base, variants in groups.items():
        variants.sort(key=lambda v: v["weight_g"] or 10**9)
        for v in variants[1:]:
            excluded.append({"raw_name": v["title"], "product_url": BASE_URL + v["path"],
                             "reason": "同一銘柄の大容量違い(最小重量100gを代表に)"})
        v = variants[0]
        time.sleep(CRAWL_DELAY_SECONDS)
        d = detail(v["path"])
        spec = d["spec"]
        parsed = parse_product(base)
        is_blend = ("ブレンド" in base or any(k in base for k in BLEND_OVERRIDES)
                    or "+" in spec.get("原産国", ""))
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            if not parsed["origin_country"]:
                src = spec.get("産地") or spec.get("原産国") or ""
                country = detect_country_name(src.split("/")[0].strip()) if src else None
                if country:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "detail_page"
            parsed = apply_category_hint_fallback(parsed, None)
            if spec.get("精製方法") and not parsed["processing_method"]:
                parsed["processing_method"] = normalize_processing_method(spec["精製方法"])
        roast_hint = spec.get("焙煎度合い") or spec.get("焙煎度合")
        if roast_hint and "★" in roast_hint:
            # 「浅煎り★★★★★☆☆深煎り」の7段階表示のみの商品: 星の数をそのまま記載する
            roast_hint = f"7段階中{roast_hint.count('★')}(1=浅煎り〜7=深煎り)"
        m = re.search(r"＜(深煎り|中深煎り|中煎り|浅煎り)ブレンド＞", v["title"])
        if m:
            roast_hint = m.group(1)
        farm = [f"{k}：{spec[k]}" for k in ("農園名", "農園主", "産地", "標高", "品種") if spec.get(k)]
        stock_status = detect_stock_status(v["title"], d["sold_out"])
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": d["notes"],
            "farm_note": " / ".join(farm) or None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": v["price"],
            "weight_g": v["weight_g"],
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": BASE_URL + v["path"],
        })
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    with open("data_arovor.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records, "excluded_variants": excluded},
                  f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_arovor.json に出力しました(大容量違い{len(excluded)}件を除外)")
