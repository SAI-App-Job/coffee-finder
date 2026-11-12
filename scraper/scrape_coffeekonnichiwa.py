# -*- coding: utf-8 -*-
"""
scrape_coffeekonnichiwa.py

珈琲こん日和(coffee-konnichiwa.com、鹿児島県奄美市名瀬港町22-18、奄美大島の自家焙煎珈琲店)の
オンラインショップの商品情報を取得する。Wix(Wix Stores)。
robots.txt は User-agent: * で Allow: / (Disallow は *?lightbox= のみ)。間隔は1.6秒。

【ページ構造について】
/store-products-sitemap.xml から全商品ページ(14ページ)を列挙し、各ページのJSON-LD(schema.org Product)から
名前・説明・価格・在庫を取得する。同一銘柄が「100g」と「400g」の別ページ(末尾「の複製」「のコピー」「-1」)で並ぶため、
銘柄名(「のコピー」「の複製」を除去)ごとに最小価格のページ=100g(/shop の一覧で100g=850〜950円、400g=3,200〜3,600円と確認)を代表にする。
ドリップバッグ5ヶ国セット・ティスティングセット(飲み比べ)は除外。
焙煎度は商品名の【DarkRoast・深煎り】【MediumRoast・中煎り】から取る(ビターブレンド・デカフェは記載なしのため null)。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "珈琲こん日和",
    "url": "https://www.coffee-konnichiwa.com/shop",
    "platform": "Wix(Wix Stores)",
    "address": "鹿児島県奄美市名瀬港町22-18",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
    "source_note": "公式 https://www.coffee-konnichiwa.com/ ・ショップ /shop ・商品サイトマップとJSON-LD・特商法 /transactionslaw を2026-11-02に確認。商品ページのlastmodは2026-10-06。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://www.coffee-konnichiwa.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 1.6
LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
EXCLUDE_KEYWORDS = ("セット", "ドリップバッ", "ドリップパ")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|浅煎り|中煎り|深煎り)")
PROCESS_PATTERN = re.compile(r"精選方法[：:]\s*([^\s、。原]{1,15})")
FLAG_PATTERN = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def fetch_ld(url: str) -> dict | None:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    m = LD_PATTERN.search(resp.text)
    return json.loads(m.group(1)) if m else None


def clean_name(raw: str) -> str:
    name = html.unescape(raw).replace("　", " ")
    name = FLAG_PATTERN.sub(" ", name)
    name = re.sub(r"(のコピー|の複製)\s*$", "", name.strip())
    name = re.sub(r"\s+", " ", name).strip()
    return name


def build_record(url: str, ld: dict) -> dict | None:
    full = clean_name(ld.get("name", ""))
    if any(kw in full for kw in EXCLUDE_KEYWORDS):
        return None
    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip() or None
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")
    roast_m = ROAST_PATTERN.search(full)
    roast = ("深煎り" if roast_m.group(1) == "極深煎り" else roast_m.group(1)) if roast_m else None
    # 表示名: 【…】の焙煎度表記を除いた銘柄名
    name = re.sub(r"\s*【[^】]*】", "", full).strip()
    parsed = parse_product(name)
    decaf = "カフェインレス" in name
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "デカフェ" if decaf else "ストレート"
        if not parsed["origin_country"]:
            parsed["origin_country"] = detect_country_name(name)
            parsed["origin_source"] = "country_name" if parsed["origin_country"] else None
    pm = PROCESS_PATTERN.search(desc or "")
    processing = parsed["processing_method"] or (detect_processing_method(pm.group(1)) if pm else None)
    flavor = (desc or "").split("生産地")[0].strip() or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": flavor,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": None,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    best: dict[str, dict] = {}
    for url in list_product_urls():
        try:
            ld = fetch_ld(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {url} ({e})")
            continue
        if not ld:
            continue
        rec = build_record(url, ld)
        if rec is None or rec["price"] is None:
            continue
        cur = best.get(rec["raw_name"])
        if cur is None or rec["price"] < cur["price"]:
            best[rec["raw_name"]] = rec
    records = list(best.values())
    for rec in records:
        # /shop の一覧で最小価格のページ(850〜950円)が100g、400gは3,200円以上と確認済み
        rec["weight_g"] = 100 if rec["price"] < 1500 else None
    return records


def main():
    records = scrape_all_products()
    with open("data_coffeekonnichiwa.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeekonnichiwa.json に出力しました")


if __name__ == "__main__":
    main()
