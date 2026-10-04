# -*- coding: utf-8 -*-
"""
scrape_lavenir.py

カフェ ラヴニール(lavenir.ocnk.net、兵庫県神戸市中央区元町高架通3-184、
神戸マイスター・橋本和也氏による自家焙煎のスペシャルティコーヒー専門店。受注焙煎)の
商品情報を取得する。おちゃのこネット(UTF-8)。

【対象商品について】
実データ確認済み(2026-10時点): 「【通常商品】レギュラーコーヒー」(product-list/95)と
「【限定商品】希少品種など」(product-list/104)が対象。重量違い(100g/200g/300g/400g/500g)が
別商品(別pid)として並ぶため、同名の銘柄は最小重量(100g)の商品を代表とし、一覧の税込価格を使う。
クリックポスト便(200g×2袋の組み合わせ)、ドリップバッグ、水出しコーヒーバッグ、ギフト詰め合わせは除外。
在庫は一覧セルの`list_item_soldout`クラスで判定する。
商品名は「【100g】コスタリカ /アキアレス農園」の形式で、重量の【】部分を除いて商品名とする。
"""

import json
import re
import time
import unicodedata
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "Café Lavenir",
    "url": "https://lavenir.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "兵庫県神戸市中央区元町高架通3-184",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(おちゃのこネット標準構成)",
}

BASE_URL = "https://lavenir.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORIES = [95, 104]
NAME_PATTERN = re.compile(r"^【(\d+)\s*g】\s*(.+)$")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
LABEL_WORDS = "原産国|地域|農園|標高|使用品種|品種|精製方法|焙煎度合|ブレンド"
LABEL_START = re.compile(r"(?:%s)\s*[：:]" % LABEL_WORDS)
LABEL_VALUE = re.compile(r"(%s)[：:\s]+(.*?)(?=\s*(?:%s)[：:\s]|$)" % (LABEL_WORDS, LABEL_WORDS))
ROAST_ONLY = re.compile(r"^(?:極|中)?(?:浅|深)?煎り$|^中煎り$")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for cat in CATEGORIES:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/product-list/{cat}"), "html.parser")
        for cell in soup.select("li.list_item_cell"):
            a = cell.select_one("a[href*='/product/']")
            pid_m = re.search(r"/product/(\d+)", a.get("href", "")) if a else None
            if not pid_m or pid_m.group(1) in seen:
                continue
            seen.add(pid_m.group(1))
            title = norm(cell.select_one(".goods_name").get_text(strip=True))
            m = NAME_PATTERN.match(title)
            if not m:
                continue  # 重量表記の無い商品(クリックポスト便・ドリップバッグ等)は対象外
            price_el = cell.select_one(".selling_price")
            pm = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            items.append({
                "pid": pid_m.group(1),
                "weight": int(m.group(1)),
                "name": m.group(2).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": "list_item_soldout" in " ".join(cell.get("class", [])),
            })
        time.sleep(0.5)
    return items


def build_record(it: dict) -> dict:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/product/{it['pid']}"), "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    text = norm_lines(soup.get_text("\n", strip=True))
    start = text.index("商品詳細") + 1 if "商品詳細" in text else 0
    end = next((i for i, ln in enumerate(text) if ln.startswith("賞味期限")), len(text))
    body = text[start:end]
    labels, desc = {}, []
    for ln in body:
        if LABEL_START.search(ln) or ROAST_ONLY.match(ln):
            continue
        if not (ln.startswith("【") and ln.endswith("】")):
            desc.append(ln)
    # 1行に「原産国:… 地域:… 標高:…」のように複数ラベルが並び、値が次行に折り返す場合もあるため、
    # 本文を連結してからラベル単位で切り出す
    joined = " ".join(ln for ln in body if not (ln.startswith("【") and ln.endswith("】")))
    for m in LABEL_VALUE.finditer(joined):
        labels.setdefault(m.group(1), m.group(2).strip())

    name = it["name"]
    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and labels.get("原産国"):
            c = detect_country_name(labels["原産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and labels.get("精製方法"):
            processing = normalize_processing_method(labels["精製方法"])
    roast_label = labels.get("焙煎度合") or ""
    hint = ROAST_HINT_PATTERN.search(roast_label)
    farm_bits = [f"{k}: {labels[k]}" for k in ("地域", "農園", "標高", "使用品種", "品種") if labels.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": hint.group(1) if hint else (roast_label or None),
        "flavor_notes": " ".join(desc)[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/product/{it['pid']}",
    }


def norm_lines(raw: str) -> list[str]:
    return [l for l in (norm(x) for x in raw.split("\n")) if l]


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
    with open("data_lavenir.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lavenir.json に出力しました")


if __name__ == "__main__":
    main()
