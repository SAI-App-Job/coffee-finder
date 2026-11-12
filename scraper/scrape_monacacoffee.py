# -*- coding: utf-8 -*-
"""
scrape_monacacoffee.py

もなか珈琲(monacacoffee.com、大阪府大阪市北区中崎3-3-13、中崎町のコーヒーロースター)の
オンラインショップから珈琲豆の商品情報を取得する。xaas3系カート。
robots.txt は /default/error/ と /preview/ のみDisallow。間隔は2秒。

【取得方法】商品一覧 /app/searchGoodsList(全23件が1ページ)の商品リンク(/item/<code>/)から、
セット・定期便・ドリップバッグ・水出しバッグ・タオル等の雑貨を除いた豆商品(シングルオリジン・ブレンド)を取り、
各商品ページの ld+json(Product.offers.price=最小価格=最小重量の価格、availability)と
重量セレクト(selVariation1)の先頭=最小重量を採用する(挽き目違いは同価格。豆のまま)。
焙煎度は商品ページの「当店での焙煎度合い」ゲージ(11段階、◆の位置)を次のように換算する:
0-2=浅煎り, 3-4=中浅煎り, 5-6=中煎り, 7-8=中深煎り, 9-10=深煎り。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "もなか珈琲",
    "url": "https://www.monacacoffee.com/",
    "platform": "xaas3",
    "address": "大阪府大阪市北区中崎3-3-13",
    "prefecture": "大阪府",
    "robots_txt_status": "取得可(/default/error/ と /preview/ のみDisallow)",
    "source_note": "公式 https://www.monacacoffee.com/ ・商品一覧 /app/searchGoodsList ・特商法 /info.html を2026-10-26に確認。新着商品(タイ ヨスニヨム農園)掲載あり。",
    "last_verified_at": "2026-10-26",
}

BASE = "https://www.monacacoffee.com"
LIST_URL = BASE + "/app/searchGoodsList"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 2.0
EXCLUDE_WORDS = ("セット", "定期便", "ドリップ", "水出し", "タオル", "手ぬぐい", "めがね", "拭き", "コールドブリュー")


def get(url: str) -> str:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def collect_items() -> list[tuple[str, str]]:
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    out = []
    for p in soup.select("p.name a[href]"):
        name = p.get_text(" ", strip=True)
        url = p["href"]
        if "/item/" not in url or any(w in name for w in EXCLUDE_WORDS):
            continue
        if all(url != u for _, u in out):
            out.append((name, url))
    return out


def roast_from_gauge(text: str) -> str | None:
    m = re.search(r"浅←[―\-─ー]+→深\s*\n?\s*([〇○◯◆]+)", text)
    if not m or "◆" not in m.group(1):
        return None
    i = m.group(1).index("◆")
    if i <= 2:
        return "浅煎り"
    if i <= 4:
        return "中浅煎り"
    if i <= 6:
        return "中煎り"
    if i <= 8:
        return "中深煎り"
    return "深煎り"


def build_record(list_name: str, url: str) -> dict | None:
    soup = BeautifulSoup(get(url), "html.parser")
    ld_tag = soup.find("script", type="application/ld+json")
    if not ld_tag or not ld_tag.string:
        return None
    ld = json.loads(ld_tag.string, strict=False)
    prod = ld[0] if isinstance(ld, list) else ld
    offer = prod.get("offers") or {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = offer.get("availability", "").endswith("InStock")
    weight = None
    sel = soup.find("select", id="selVariation1")
    if sel:
        for o in sel.find_all("option"):
            m = re.match(r"^\s*(\d+)\s*g\s*$", o.get_text(strip=True))
            if m:
                weight = int(m.group(1))
                break
    text = soup.get_text("\n", strip=True)
    name = re.sub(r"\s+", " ", list_name.replace("　", " ")).strip()
    name = re.sub(r"^〈[^〉]*〉\s*", "", name)
    parsed = parse_product(name)
    fm = re.search(r"“([^”]+)”", text)
    sm = re.search(r"精製[：:]\s*([^\n]+)", text)
    is_blend = name.startswith("ブレンド")
    cm = re.match(r"^【([^】]+)】", name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"] and cm:
            from coffee_parser import detect_country_name
            parsed["origin_country"] = detect_country_name(cm.group(1)) or ({"タイ": "タイ"}.get(cm.group(1)))
            parsed["origin_source"] = "country_name" if parsed["origin_country"] else None
    if "カフェインレス" in name or "デカフェ" in name:
        pass
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_from_gauge(text),
        "roast_hint": None,
        "flavor_notes": fm.group(1) if fm else None,
        "farm_note": sm.group(1)[:100] if sm and not is_blend else None,
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
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_monacacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_monacacoffee.json に出力しました")


if __name__ == "__main__":
    main()
