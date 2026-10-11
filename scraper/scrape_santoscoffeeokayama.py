# -*- coding: utf-8 -*-
"""
scrape_santoscoffeeokayama.py

珈琲工房サントス(santos-coffee.net、岡山県岡山市北区富田531-2、コーヒー豆通販・業務用販売)の
商品情報を取得する。WordPress + Welcart(UTF-8)。
※新潟県の「SANTOS」(scrape_santoscoffee.py、santos-coffee.jp)とは別の店舗のため別名にしている。

【対象商品について】
実データ確認済み(2026-10時点): /item/coffee/(3ページ、全26件)を巡回する。
商品名末尾に商品コード(CS=単一産地、CB/MB=ブレンド)が付く(例「キリマンジャロCS106」)。
商品コードは商品名から除去し、CSはストレート・CB/MBはブレンドとして扱う。
「水出しコーヒーバック 50g×2袋入り」(CB200)と「お試しコーヒー豆(60g×3袋)」(CB999)は
バッグ・セットのため除外し、24件を収録する。
価格は税込で、100gあたり(ページ内「100gから販売」、数量1=100g)。重量は100gとする。
在庫は商品ページの「在庫状態 : 在庫有り / 入荷待ち」から判定し、入荷待ちは完売とする。
焙煎度は商品ページには一貫した表記が無いため、店が分類している「焙煎から選ぶ」
(/item/baisen/<浅煎り〜極深煎り>)の所属カテゴリから取る(所属が無い商品はnull)。
産地は単一産地では商品名の先頭語(国名)から、味わいは「テイスト(味わい・風味)」欄から取る。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲工房サントス",
    "url": "https://santos-coffee.net/",
    "platform": "WordPress+Welcart",
    "address": "岡山県岡山市北区富田531-2",
    "prefecture": "岡山県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://santos-coffee.net"
LIST_URL = f"{BASE_URL}/item/coffee/"
MAX_PAGES = 8
DELAY = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("バック", "バッグ", "お試し", "セット", "ギフト", "ドリップ")

# 「焙煎から選ぶ」カテゴリ(スラッグ -> 焙煎度表記)
ROAST_CATEGORIES = {
    "asairi": "浅煎り",
    "chu-asairi": "中浅煎り",
    "chuiri": "中煎り",
    "chu-fukairi": "中深煎り",
    "fukairi": "深煎り",
    "italian-roast": "極深煎り",
}

PRICE_PATTERN = re.compile(r"[¥￥]\s*([\d,]+)")
CODE_PATTERN = re.compile(r"\s*([A-Z]{2}\d{3})\s*$")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def paged(url: str):
    for page in range(1, MAX_PAGES + 1):
        yield page, (url if page == 1 else f"{url}page/{page}")


def list_items() -> list[dict]:
    items, seen = [], set()
    for page, url in paged(LIST_URL):
        try:
            soup = BeautifulSoup(fetch(url), "html.parser")
        except requests.HTTPError:
            break
        new = 0
        for li in soup.select("ul.item-archive li.item"):
            a = li.select_one("h2.item-title a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            title = unicodedata.normalize("NFKC", a.get_text("", strip=True))
            title = re.sub(r"\s+", " ", title).strip()
            items.append({"title": title, "url": href})
        if new == 0:
            break
        time.sleep(DELAY)
    return items


def roast_map() -> dict[str, str]:
    mapping = {}
    for slug, roast in ROAST_CATEGORIES.items():
        for page, url in paged(f"{BASE_URL}/item/baisen/{slug}/"):
            try:
                soup = BeautifulSoup(fetch(url), "html.parser")
            except requests.HTTPError:
                break
            links = [a.get("href", "") for a in soup.select("ul.item-archive h2.item-title a")]
            if not links:
                break
            for href in links:
                mapping.setdefault(href, roast)
            time.sleep(DELAY)
    return mapping


NOTICE_PATTERN = re.compile(r"在庫が入れ替わ|価格|^\d{2,4}/\d{1,2}|^[~¥]|⇒|/\s*100g|中東情勢|洪水被害|^2025年|にあがります|に上がります|^\d+円")


def extract_taste(text: str) -> str | None:
    """「テイスト(味わい・風味)」欄の味わい説明を取る。冒頭に価格改定などのお知らせが
    入る商品があるため、「» 味わい」「【味を想像してください】」以降、無ければ
    お知らせ行を飛ばした先頭から取る。"""
    if "テイスト(味わい・風味)" not in text:
        return None
    seg = text.split("テイスト(味わい・風味)", 1)[1]
    seg = re.split(r"焙煎士オススメ|コーヒーチャート", seg, 1)[0]
    lines = [ln.strip() for ln in seg.split("\n") if ln.strip()]
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("» 味わい") or ln.startswith("【味を想像してください】"):
            start = i + 1
            break
    if start is None:
        start = 0
        while start < len(lines) and NOTICE_PATTERN.search(lines[start]):
            start += 1
    body = []
    for ln in lines[start:]:
        if ln.startswith("»") or ln in ("»",):
            ln = ln.lstrip("» ").strip()
            if not ln:
                continue
        body.append(ln)
    out = "".join(body)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > 140:
        cut = out[:140]
        out = cut[: max(cut.rfind("。"), 0) + 1] if "。" in cut else cut
    return out or None


def fetch_detail(url: str) -> dict:
    soup = BeautifulSoup(fetch(url), "html.parser")
    text = soup.get_text("\n", strip=True)
    price_m = re.search(r"販売価格\s*】\s*\n?\s*[¥￥]\s*([\d,]+)", text)
    stock_m = re.search(r"在庫状態\s*[:：]\s*(\S+)", text)
    taste = extract_taste(text)
    return {
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "stock": stock_m.group(1) if stock_m else None,
        "taste": taste,
    }


def build_record(item: dict, detail: dict, roast: str | None) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    code_m = CODE_PATTERN.search(title)
    code = code_m.group(1) if code_m else ""
    name = CODE_PATTERN.sub("", title).strip()
    is_blend = code.startswith(("CB", "MB")) or "ブレンド" in name

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            d = detect_country_name(name)
            if d:
                parsed["origin_country"] = d
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    stock = detail["stock"] or ""
    sold_out = stock not in ("在庫有り", "在庫あり")
    price = detail["price"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": detail["taste"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    items = list_items()
    roasts = roast_map()
    records = []
    for item in items:
        if any(kw in item["title"] for kw in EXCLUDE_KEYWORDS):
            continue
        detail = fetch_detail(item["url"])
        time.sleep(DELAY)
        record = build_record(item, detail, roasts.get(item["url"]))
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_santoscoffeeokayama.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_santoscoffeeokayama.json に出力しました")


if __name__ == "__main__":
    main()
