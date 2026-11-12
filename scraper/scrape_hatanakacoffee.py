# -*- coding: utf-8 -*-
"""
scrape_hatanakacoffee.py

HATANAKA COFFEE(ハタナカコーヒー、鹿児島県鹿児島市易居町6-1ほか計3店舗、1988年創業の自家焙煎店)の
オンラインショップ(hatanakacoffee.jp、xaas3系カート)からコーヒー豆の商品情報を取得する。
robots.txt は /default/error/ と /preview/ のみDisallow。間隔は2秒。

【取得方法】商品一覧 /app/categoryGoodsList(全16件が1ページ)の商品リンク(/item/<code>/)から、
各商品ページを取得する。価格表示は「100g価格 ～ 4袋/1kg価格」の範囲表示で、先頭が最小重量(100g)の価格。
容量セレクト(selVariation2)の先頭が100g であることを確認して採用する(豆/挽きは同価格、豆のまま)。
単一産地は説明文の「焙煎度合：」「テイスト：」「精選方法：」を採用する。ブレンド(No.1〜7)は焙煎度の記載がないため null。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "HATANAKA COFFEE",
    "url": "https://www.hatanakacoffee.jp/",
    "platform": "xaas3",
    "address": "鹿児島県鹿児島市易居町6-1",
    "prefecture": "鹿児島県",
    "robots_txt_status": "取得可(/default/error/ と /preview/ のみDisallow)",
    "source_note": "公式 https://www.hatanakacoffee.jp/ ・商品一覧 /app/categoryGoodsList ・店舗案内 /shop.html ・特商法 /info.html を2026-11-02に確認。",
    "last_verified_at": "2026-11-02",
}

BASE = "https://www.hatanakacoffee.jp"
LIST_URL = BASE + "/app/categoryGoodsList"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 2.0
EXCLUDE_WORDS = ("セット", "定期便", "ドリップ", "ギフト", "詰め合わせ", "福袋")


def get(url: str) -> str:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def collect_items() -> list[tuple[str, str]]:
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    out = []
    for p in soup.select("p.name a[href]"):
        name = re.sub(r"\s+", " ", p.get_text(" ", strip=True).replace("　", " ")).strip()
        url = p["href"]
        if "/item/" not in url or any(w in name for w in EXCLUDE_WORDS):
            continue
        if all(url != u for _, u in out):
            out.append((name, url))
    return out


def field(text: str, label: str) -> str | None:
    m = re.search(label + r"\s*[：:]\s*([^\n]+)", text)
    return m.group(1).strip() if m else None


def build_record(list_name: str, url: str) -> dict | None:
    soup = BeautifulSoup(get(url), "html.parser")
    text = soup.get_text("\n", strip=True)
    # 価格(先頭=最小重量)
    pm = re.search(r'<span id="spnSalesPrice1">\s*<span class="price">([\d,]+)</span>', str(soup))
    price = int(pm.group(1).replace(",", "")) if pm else None
    # 容量セレクトの先頭が100gであること
    weight = None
    sel = soup.find("select", id="selVariation2")
    if sel:
        for o in sel.find_all("option"):
            m = re.match(r"^\s*(\d+)\s*[gｇ]\s*$", o.get_text(strip=True))
            if m:
                weight = int(m.group(1))
                break
    in_stock = "在庫あり" in text and "在庫切れ" not in text
    name = list_name
    parsed = parse_product(name)
    is_blend = bool(re.match(r"^No\.\d", name)) or "ブレンド" in name
    # 説明文の構造化項目(焙煎度合・テイスト・精選方法)
    roast = field(text, r"焙煎度合")
    taste = field(text, r"テイスト")
    method = field(text, r"精選方法")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            cm = name.split(" ")[0]
            parsed["origin_country"] = detect_country_name(cm)
            parsed["origin_source"] = "country_name" if parsed["origin_country"] else None
        if not parsed["origin_country"] and name.startswith("バリ"):
            parsed["origin_country"] = "インドネシア"
            parsed["origin_source"] = "region_name"
    if method and not parsed["processing_method"]:
        from coffee_parser import normalize_processing_method
        parsed["processing_method"] = normalize_processing_method(method)
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
        "flavor_notes": taste,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for name, url in collect_items():
        rec = build_record(name, url)
        if rec and rec["price"]:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_hatanakacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hatanakacoffee.json に出力しました")


if __name__ == "__main__":
    main()
