# -*- coding: utf-8 -*-
"""
scrape_bongencoffee.py

BONGEN COFFEE(bongen-shirafushi-coffee.com、東京都中央区銀座2-16-3の銀座本店(BONGENCOFFEE
TOKYO GINZA)。運営は株式会社座御堂。銀座本店・銀座 本丸・日本橋店・BONGEN BEANS STORE GINZA等の
少数店舗で11店舗未満。「珈琲豆の選定、仕入れ、保管、焙煎まで全て独自(自社ロースター)」と明記)の
商品情報を取得する。Shopify。白節(SHIRAFUSHI ROASTERS)ブランドの上位ラインも同じサイトで販売される。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`は約120商品(器具・ギフト・セット・
定期便・ドリップバッグ・大容量1kgパック等を含む)。このうちコーヒー豆の単品24銘柄
(ブレンド8前後・ストレート・ゲイシャ・デカフェ)をBEAN_HANDLESで明示して対象とする。
バリエーションは「豆」「粉(細挽き/中挽き/粗挽き)」で価格は同額のため「豆」を代表とし、在庫も
豆バリエーションで判定する。内容量はvariantのgramsが梱包重量のため使わず、商品ページ本文の
「内容量：200g」等から取る(取得できなければNone)。産地は商品名にない場合(雲嶺松・白嶺松等の
日本語名)があるため、ページ本文の「生豆生産国」から補う。
"""

import json
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BONGEN COFFEE",
    "url": "https://bongen-shirafushi-coffee.com/",
    "platform": "Shopify",
    "address": "東京都中央区銀座2-16-3",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

API_BASE = "https://bongen-shirafushi-coffee.com"
PRODUCT_BASE = "https://bongen-shirafushi-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.IGNORECASE)

# ハンドル別の分類・産地の上書き(商品名から判定できないもの)
CATEGORY_OVERRIDES = {}
ORIGIN_OVERRIDES = {}
# 商品名の語から誤判定される精選方法の上書き(ハンドル: 精選方法)
PROCESSING_OVERRIDES = {}


def to_grams(label: str) -> int | None:
    m = WEIGHT_PATTERN.search(label or "")
    if not m:
        return None
    value = float(m.group(1))
    return int(round(value * 1000)) if m.group(2).lower() == "kg" else int(round(value))


def html_text(html: str | None) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True))


def pick_offer(p: dict, body: str) -> tuple[int | None, int, bool] | None:
    """最小重量のバリエーションを代表とし、(重量g, 価格, 在庫あり)を返す。"""
    weighted = []
    for v in p["variants"]:
        w = to_grams(v.get("title") or "")
        if w:
            weighted.append((w, v))
    if not weighted:
        return None
    weight = min(w for w, _ in weighted)
    same = [v for w, v in weighted if w == weight]
    available = any(v.get("available") for v in same)
    return weight, int(float(same[0]["price"])), available


def extra_origin(p: dict, body: str) -> str | None:
    """商品名から産地を判定できない場合の追加判定(店舗ごとに上書きする)。"""
    return None


BEAN_HANDLES = [
    "nihonbashi-blend", "panama-geisha-natural", "thailand-natural", "unreisho", "hakureisho", "chikuei",
    "fushitora", "ethiopia-honey", "nicaragua-natural", "colombia-natural", "honduras-natural",
    "bongen-premium-blend", "bongen-premium-fruity-blend", "ultra-dark-roasted-naturally-grown-in-uganda",
    "tigers-tail", "bongen-decaf", "costa-rica-geisha", "panama-geisha", "good-old-blend", "ginza-blend",
    "uganda-naturally-cultivated-coffee-beans", "fragrance_kenya", "charcoal-grill-colombia", "bongen-original-blend",
]

PAGE_CACHE: dict[str, str] = {}


def page_text(p: dict) -> str:
    handle = p["handle"]
    if handle not in PAGE_CACHE:
        resp = requests.get(f"{PRODUCT_BASE}/products/{urllib.parse.quote(handle)}", headers=REQUEST_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        PAGE_CACHE[handle] = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        time.sleep(0.8)
    return PAGE_CACHE[handle]


def include_product(p: dict) -> bool:
    return p["handle"] in BEAN_HANDLES


def make_name(p: dict) -> str:
    return re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()


def pick_offer(p: dict, body: str):
    beans = [v for v in p["variants"] if (v.get("title") or "").strip() in ("豆", "Default Title")] or p["variants"][:1]
    v = beans[0]
    m = re.search(r"内容量[:：]\s*(\d+)\s*g", page_text(p))
    return (int(m.group(1)) if m else None), int(float(v["price"])), bool(v.get("available"))


def extra_origin(p: dict, body: str) -> str | None:
    m = re.search(r"生豆生産国[:：]\s*([^\s]+)", page_text(p))
    if not m or "ブレンド" in p["title"] or "BLEND" in p["title"].upper():
        return None
    return detect_country_name(m.group(1))


def product_url(p: dict) -> str:
    return f"{PRODUCT_BASE}/products/{urllib.parse.quote(p['handle'])}"

def detect_roast(name: str, p: dict, body: str) -> str | None:
    tags = p.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    found = {m.group(1) for t in tags for m in [ROAST_PATTERN.search(t)] if m}
    return found.pop() if len(found) == 1 else None



def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(f"{API_BASE}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        batch = resp.json().get("products", [])
        if not batch:
            break
        products += batch
        if len(batch) < 250:
            break
        page += 1
    return products


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        if not include_product(p):
            continue
        name = make_name(p)
        body = html_text(p.get("body_html"))
        offer = pick_offer(p, body)
        if offer is None:
            continue
        weight, price, available = offer

        handle = p["handle"]
        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        category = CATEGORY_OVERRIDES.get(handle)
        if category:
            parsed["category"] = category
        if parsed["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["origin_country"]:
                extra = extra_origin(p, body)
                if extra:
                    parsed["origin_country"] = extra
                    parsed["origin_source"] = "description"
            if handle in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[handle]
                parsed["origin_source"] = "raw_name"

        if handle in PROCESSING_OVERRIDES:
            parsed["processing_method"] = PROCESSING_OVERRIDES[handle]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": detect_roast(name, p, body) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": body[:400] or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": product_url(p),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bongencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bongencoffee.json に出力しました")


if __name__ == "__main__":
    main()
