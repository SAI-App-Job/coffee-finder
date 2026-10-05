# -*- coding: utf-8 -*-
"""
scrape_nakayamabaisenjo.py

中山珈琲焙煎所(NAKAYAMA COFFEE ROASTERY、nakayamacoffee.com、京都府木津川市
南加茂台9丁目15-2)の商品情報を取得する。カラーミーショップ(shop-pro.jp、独自ドメイン、
EUC-JP)。※ scrape_nakayamacoffee.py(沖縄の中山コーヒー園)とは別の店舗。

【対象商品について】
実データ確認済み: サイト内検索(?mode=srh)の全39件のうち、商品名が「100g」「200g」で
始まる焙煎豆を対象とする。同一銘柄が100g・200gの別商品として並ぶため、銘柄ごとに
最小重量の商品を代表とする。ドリップバッグ・LIQUID(リキッドコーヒー、ギフト含む)・
COLD BREW(水出しパック)・「おまかせ3種類」(セット)・SHOPPING BAG・WRAPPING・お知らせは除外。

【価格・在庫について】
価格は税込(sales_price_including_tax)。在庫は商品ページのカートボタンが「sold out」
(disabled)、またはColorme.product.stock_numが0のとき完売とする。

【商品説明について】
商品ページの「AREA / PRODUCER / VARIETAL / PROCESS / ALTITUDE / ROAST / NOTE」の
構造化表記から精製方法・生産者・品種・標高・テイスティングノートを取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "中山珈琲焙煎所",
    "url": "https://www.nakayamacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "京都府木津川市南加茂台9丁目15-2",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(カラーミーショップ標準構成)",
}

BASE_URL = "https://www.nakayamacoffee.com/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
WEIGHT_PREFIX = re.compile(r"^\s*(\d+)\s*g\s+", re.I)
EXCLUDE_KEYWORDS = ("DRIP BAG", "ドリップバッグ", "LIQUID", "COLD BREW", "おまかせ", "SHOPPING BAG", "WRAPPING", "GIFT")
ROAST_IN_PAREN = re.compile(r"（([^）]*)）")
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)
ROAST_EN = {"light": "浅煎り", "medium-light": "中浅煎り", "medium": "中煎り",
            "medium-dark": "中深煎り", "dark": "深煎り"}
FACT_KEYS = "AREA|PRODUCER|SUPPLIER|VARIETAL|PROCESS|ALTITUDE|ROAST|NOTE"


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    for page in range(1, 20):
        html = fetch(f"{BASE_URL}?mode=srh&cid=&keyword=&sort=n&page={page}")
        new = [i for i in dict.fromkeys(re.findall(r"pid=(\d+)", html)) if i not in ids]
        if not new:
            break
        ids += new
    return ids


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def parse_detail(pid: str) -> dict | None:
    html = fetch(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    raw_title = product.get("name") or ""
    title = re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", raw_title)).strip()
    wm = WEIGHT_PREFIX.match(title)
    if not wm or any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
        return None
    weight = int(wm.group(1))
    name = WEIGHT_PREFIX.sub("", title).strip()

    soup = BeautifulSoup(html, "html.parser")
    btn = soup.select_one(".product-order-input button")
    sold_out = product.get("stock_num") == 0 or bool(btn and "sold out" in btn.get_text().lower())

    exp = soup.select_one("div.product-order-exp")
    lines = []
    if exp:
        for br in exp.find_all("br"):
            br.replace_with("\n")
        lines = [l.strip() for l in exp.get_text().split("\n") if l.strip()]
    facts = {}
    for l in lines:
        fm = re.match(rf"^({FACT_KEYS})\s*:\s*(.+)$", l)
        if fm and fm.group(1) not in facts:
            facts[fm.group(1)] = fm.group(2).strip()
    # 説明本文: 構造化行・レシピ以降を除く
    body = []
    for l in lines:
        if l.startswith("|| おすすめレシピ"):
            break
        if re.match(rf"^({FACT_KEYS}|DECAF PROCESS)\s*:", l) or re.match(r"^\{.*\}$", l):
            continue
        body.append(l)
    desc_text = " ".join(body)

    return {
        "pid": pid, "name": name, "weight": weight, "price": product.get("sales_price_including_tax"),
        "sold_out": sold_out, "facts": facts, "desc": desc_text,
    }


def build_record(d: dict) -> dict:
    name = d["name"]
    facts = d["facts"]
    is_blend = "ブレンド" in name or "BLEND" in name.upper()
    parsed = parse_product(name)
    name_for_country = name.replace("-", " ")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        detected = detect_country_name(name_for_country)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        else:
            detected = detect_country_name(d["desc"])
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_level, roast_hint = (None, None)
    pm = ROAST_IN_PAREN.search(name)
    if pm:
        roast_level, roast_hint = coarse_roast(pm.group(1))
    if not roast_level and facts.get("ROAST"):
        roast_level = ROAST_EN.get(facts["ROAST"].lower())

    processing = None if is_blend else detect_processing_method(facts.get("PROCESS", ""))
    farm_parts = []
    if facts.get("PRODUCER") or facts.get("SUPPLIER"):
        farm_parts.append("生産者: " + (facts.get("PRODUCER") or facts.get("SUPPLIER")))
    if facts.get("AREA"):
        farm_parts.append("地域: " + facts["AREA"])
    if facts.get("VARIETAL"):
        farm_parts.append("品種: " + facts["VARIETAL"])
    if facts.get("ALTITUDE"):
        farm_parts.append("標高: " + facts["ALTITUDE"])
    notes = facts.get("NOTE")
    flavor_notes = (notes + " / " if notes else "") + d["desc"][:300]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes.strip(" /") or None,
        "farm_note": " / ".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": "完売" if d["sold_out"] else "販売中",
        "out_of_stock": d["sold_out"],
        "product_url": f"{BASE_URL}?pid={d['pid']}",
    }


def scrape_all_products() -> list[dict]:
    details = []
    for pid in collect_product_ids():
        try:
            d = parse_detail(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if d:
            details.append(d)
    # 銘柄(重量表記を除いた商品名)ごとに最小重量の商品を代表とする
    best = {}
    for d in details:
        if d["name"] not in best or d["weight"] < best[d["name"]]["weight"]:
            best[d["name"]] = d
    return [build_record(d) for d in best.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_nakayamabaisenjo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nakayamabaisenjo.json に出力しました")


if __name__ == "__main__":
    main()
