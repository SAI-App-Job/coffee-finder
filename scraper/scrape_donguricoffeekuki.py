# -*- coding: utf-8 -*-
"""
scrape_donguricoffeekuki.py

自家焙煎珈琲屋どんぐり(埼玉県久喜市青葉。donguri-coffee.shop-pro.jp、カラーミーショップ、
charset=EUC-JP)の商品情報を取得する。川口市の「どんぐりの木」(別店・登録済み)とは無関係。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、3ページ)の全商品から、ギフトセット・お試しセット・
ドリップバッグ・フィルターを除いた豆銘柄。1商品に「豆(100g)/粉(100g)-挽き方/ドリップバッグ(5バッグ)」の
選択肢があるため、豆(100g)のバリアントを代表にする。価格は豆でも粉でも同一。
【焙煎度】説明冒頭の「【中深煎り】」形式から取得(商品ごとに固定)。
【在庫】Colorme.inventory_control が none で構造化された在庫情報は無い。ページに「SOLD OUT」等の
表記があれば品切れとする。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲屋どんぐり",
    "url": "https://donguri-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "埼玉県久喜市青葉4-1-20",
    "prefecture": "埼玉県",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "https://donguri-coffee.shop-pro.jp/ の商品一覧と各商品ページ、特商法(?mode=sk)、"
                   "公式 https://donguricoffee.com/ を2026-10-26に確認。公式サイトは2025年表記、ショップは稼働中。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://donguri-coffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップバッグ", "フィルター", "おうちCoffee", "お試し")
COLORME_JSON = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
ROAST_BRACKET = re.compile(r"【(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)】")
FARM_LABELS = ("生産地域", "自然条件", "品種", "栽培方法", "精選方法")


def fetch(url: str) -> BeautifulSoup:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def list_items() -> list[dict]:
    items: dict[str, str] = {}
    for page in range(1, 6):
        soup, _ = fetch(LIST_URL + ("" if page == 1 else f"&page={page}"))
        new = 0
        for li in soup.select("li.c-item-list__item"):
            a = li.select_one(".c-item-list__ttl a")
            m = re.search(r"pid=(\d+)", a["href"]) if a else None
            if not m or m.group(1) in items:
                continue
            new += 1
            items[m.group(1)] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if new == 0:
            break
    return [{"pid": k, "name": v} for k, v in items.items()]


def pick_bean_variant(variants: list[dict]):
    """「豆(100g)」のバリアントを代表にする(粉・ドリップバッグは除く)。"""
    best = None
    for v in variants:
        label = unicodedata.normalize("NFKC", v.get("option1_value") or "")
        if "ドリップバッグ" in label or "粉" in label:
            continue
        m = WEIGHT_PATTERN.search(label)
        if not m:
            continue
        g = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
        if best is None or g < best[0]:
            best = (g, v.get("option_price_including_tax"))
    return best


def build_record(item: dict) -> dict | None:
    url = f"{BASE_URL}?pid={item['pid']}"
    soup, raw = fetch(url)
    title_el = soup.select_one("h2.p-product-info__ttl")
    title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)).strip() if title_el else item["name"]
    title = unicodedata.normalize("NFKC", title).replace("＜", "<").replace("＞", ">")
    title = re.sub(r"\s+", " ", title)

    m = COLORME_JSON.search(raw)
    product = json.loads(m.group(1)).get("product") if m else None
    picked = pick_bean_variant(product.get("variants", [])) if product else None
    if not picked:
        return None
    weight, price = picked

    body = soup.select_one("div.p-product-explain__body")
    lines = [l.strip() for l in body.get_text("\n", strip=True).split("\n") if l.strip()] if body else []
    text = "\n".join(lines)
    rm = ROAST_BRACKET.search(text)
    roast_level = rm.group(1) if rm else None
    if not roast_level:
        rm2 = re.search(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)", title)
        roast_level = rm2.group(1) if rm2 else None

    tagline = None
    farm_parts = []
    for i, l in enumerate(lines):
        if ROAST_BRACKET.fullmatch(l):
            if i + 1 < len(lines) and not lines[i + 1].startswith(("◆", "「", "●")):
                tagline = lines[i + 1]
        if l in FARM_LABELS and i + 1 < len(lines):
            farm_parts.append(f"{l}: {lines[i + 1]}")

    parsed = parse_product(title)
    if "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if not c and "インディア" in title:
                c = "インド"
            if not c:
                c = detect_country_name(" ".join(farm_parts))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    main_text = soup.select_one("div.p-product-main").get_text(" ", strip=True) if soup.select_one("div.p-product-main") else ""
    out_of_stock = bool(re.search(r"SOLD\s*OUT|売り切れ|在庫なし|品切れ|入荷待ち", main_text, re.I))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": tagline,
        "farm_note": " / ".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(k in item["name"] for k in EXCLUDE_KEYWORDS):
            continue
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_donguricoffeekuki.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_donguricoffeekuki.json に出力しました")


if __name__ == "__main__":
    main()
