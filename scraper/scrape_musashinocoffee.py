# -*- coding: utf-8 -*-
"""
scrape_musashinocoffee.py

武蔵野珈琲(6340coffee.shop-pro.jp、岡山県岡山市北区中仙道57-101、公式サイト
musashino-coffee.jp)の自家焙煎豆ネットショップの商品情報を取得する。
カラーミーショップ(EUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): 豆のカテゴリ4つ(珈琲豆(ストレート)=14件・
珈琲豆(ブレンド)=6件・珈琲豆(ﾌﾚﾝﾁ/深煎り)=5件・珈琲豆(オーガニック)=2件)を巡回する。
ドリップバッグ・ドリップコーヒー(窒素ガス充填パック)・アイスコーヒー(リキッド/バッグ)・
ルイボスティー・Myカフェセレクト(チョコ/缶)・オリジナルギフト・備品は対象外。
全商品が100g売り(商品名末尾「／100g」)で、挽き方のみ選択(重量・価格のバリエーション無し)。
オーガニックカテゴリの「東ティモール(中深煎り)」「マウント・エルゴン(中深煎り)」は
ストレートカテゴリの「東ティモール(オーガニック)」「マウント・エルゴン(オーガニック)」と
同一銘柄(説明文・価格同一、商品IDのみ別)のため、先に出現したストレート側を代表とする。
詳細ページ本文の「産地:○○。」から産地、「中位の焙煎です」「軽い深煎りです」「中深煎りです」
から焙煎度を取る(ブレンドは記載なし)。在庫切れ表示は全商品で確認できず販売中扱い。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "武蔵野珈琲",
    "url": "https://6340coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "岡山県岡山市北区中仙道57-101",
    "prefecture": "岡山県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://6340coffee.shop-pro.jp/"
BEAN_CATEGORIES = ["874882", "874884", "874885", "1186762"]  # ストレート/ブレンド/フレンチ・深煎り/オーガニック
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップ", "セット", "ギフト", "ティー", "Bag", "Ｂａｇ", "リキッド", "チョコ")
DELAY = 1

PRICE_PATTERN = re.compile(r"([\d,]+)円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PHRASES = [
    ("中深煎り", "中深煎り"),
    ("軽い深煎り", "中深煎り"),
    ("中位の焙煎", "中煎り"),
]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("euc-jp", errors="replace")


def list_items() -> list[dict]:
    items, seen_pid, seen_base = [], set(), set()
    for cb in BEAN_CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}?mode=cate&cbid={cb}&csid=0&page={page}"
            soup = BeautifulSoup(fetch(url), "html.parser")
            new = 0
            for cap in soup.select("div.caption"):
                link = cap.select_one("a[href*='pid=']")
                if not link:
                    continue
                href = link["href"]
                if href in seen_pid:
                    continue
                seen_pid.add(href)
                new += 1
                # html.parserでは壊れたマークアップ(<p>の入れ子)のためテキスト行から取る
                lines = [ln.strip() for ln in cap.get_text("\n", strip=True).split("\n") if ln.strip()]
                title = re.sub(r"\s+", " ", lines[0]) if lines else ""
                price = None
                for ln in lines[1:]:
                    pm = PRICE_PATTERN.search(ln)
                    if pm:
                        price = int(pm.group(1).replace(",", ""))
                        break
                base = re.sub(r"[（(].*?[）)]", "", title.split("／")[0]).strip()
                if base in seen_base:
                    continue
                seen_base.add(base)
                items.append({"title": title, "href": href, "price": price})
            if new == 0:
                break
            page += 1
            time.sleep(DELAY)
    return items


def fetch_detail(href: str) -> dict:
    soup = BeautifulSoup(fetch(BASE_URL + href), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    head, _, rest = text.partition("購入数")
    m = re.search(r"産地[：:]\s*([^\n。]+)", rest)
    country = m.group(1).strip() if m else None
    roast = None
    for phrase, val in ROAST_PHRASES:
        if phrase in rest.split("をお選びください")[0]:
            roast = val
            break
    # 説明文: 産地行と挽き方案内を除く
    desc_lines = []
    for line in rest.split("\n"):
        line = line.strip()
        if not line or line.startswith("産地") or line.startswith("豆のまま") or "オプション" in line:
            continue
        if line.startswith("特定商取引法"):
            if desc_lines:
                break
            continue
        if line.startswith("»") or line in ("»", "豆の状態", "中挽き(通常)", "粗挽き(プレス)", "細挽き", "エスプレッソ用", "販売価格"):
            continue
        desc_lines.append(line)
    desc = " ".join(desc_lines).strip() or None
    sold_out = bool(re.search(r"売り切れ|SOLD ?OUT|在庫切れ|品切れ", text))
    return {"country": country, "roast": roast, "desc": desc, "sold_out": sold_out}


def build_record(item: dict, detail: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", title)
    weight_m = WEIGHT_PATTERN.search(norm)
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*[／/]\s*\d+\s*g\s*$", "", norm).strip()
    name = re.sub(r"\s+", " ", name)

    parsed = parse_product(name)
    is_blend = "ブレンド" in name and "フレンチ" not in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        country = detail["country"]
        if country and not parsed["origin_country"]:
            parsed["origin_country"] = country
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            d = detect_country_name(name)
            if d:
                parsed["origin_country"] = d
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    sold_out = detail["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ("深煎り" if "(深煎り)" in name else None) or parsed["roast_level"] or detail["roast"],
        "roast_hint": None,
        "flavor_notes": detail["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}{item['href']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        detail = fetch_detail(item["href"])
        time.sleep(DELAY)
        record = build_record(item, detail)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_musashinocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_musashinocoffee.json に出力しました")


if __name__ == "__main__":
    main()
