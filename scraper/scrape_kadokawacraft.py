# -*- coding: utf-8 -*-
"""
scrape_kadokawacraft.py

角川クラフト 東所沢焙煎所(KADOKAWA CRAFT ROASTERY & CAFE オンラインショップ。
https://www.kadokawa-craft.com/ 、独自ドメインEC)の商品情報を取得する。

【商品一覧】カテゴリページ(/ic/...)は一覧がJS描画で静的HTMLに商品が載らないため、sitemap.xml の
/i/<商品記号> を対象にする。-db 付き(ドリップバッグ)・ギフト・お試しセット等は除外。
【価格・重量】商品ページのJSON-LD(Product.offers.price、税込)が既定の選択肢(100g・豆のまま)の価格。
重量・状態(豆/粉)の選択肢はページ内テンプレートAPI /api/front/template/formSelection?item_no=…
(商品ページ自身が読み込む部品)から取得し、最小重量×「豆」を代表にする。選択肢の加算額(data-rate)
は価格に加算する。
【焙煎度】本文の「焙煎度　：　中深煎り」。【在庫】JSON-LDのavailability。
robots.txt は 404(2026-10-26確認。制限の記載なし)。
"""

import json
import re
import time
import unicodedata
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "角川クラフト 東所沢焙煎所",
    "url": "https://www.kadokawa-craft.com/",
    "platform": "独自ドメインEC",
    "address": "埼玉県所沢市東所沢和田2-17-11 グランドウール東所沢101",
    "prefecture": "埼玉県",
    "robots_txt_status": "robots.txt なし(404、2026-10-26確認。制限の記載なし)",
    "source_note": "https://www.kadokawa-craft.com/ の sitemap.xml・各商品ページ・フッターの焙煎所住所(2026-10-26確認)。"
                   "お知らせは2026-10-22更新。住所は焙煎所(カフェは所沢市東所沢和田3-11-1 久保田ビル1F)を採用。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.kadokawa-craft.com"
SITEMAP_URL = BASE_URL + "/sitemap.xml"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
EXCLUDE_SLUG = re.compile(r"(-db($|-)|gift|otameshi|dripbag|set$|-set)", re.I)
EXCLUDE_TITLE = ("ドリップバッグ", "ギフト", "セット", "お試し", "詰め合わせ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
ROAST_PATTERN = re.compile(r"焙煎度\s*[:：]\s*(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def get(url: str) -> str:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_slugs() -> list[str]:
    xml = get(SITEMAP_URL)
    slugs = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        m = re.match(re.escape(BASE_URL) + r"/i/([^/?#]+)$", loc)
        if m and not EXCLUDE_SLUG.search(unquote(m.group(1))):
            slugs.append(m.group(1))
    return slugs


def pick_variant(form_html: str, base_price: int):
    """formSelectionの「量」「状態」から(最小重量, 豆のままの価格)を返す。"""
    soup = BeautifulSoup(form_html, "html.parser")
    weights, states = [], []
    for sel in soup.find_all("select"):
        label = (sel.find_parent("div").get_text(" ", strip=True) if sel.find_parent("div") else "")
        opts = []
        for o in sel.find_all("option"):
            txt = unicodedata.normalize("NFKC", o.get_text(" ", strip=True))
            opts.append((txt, int(o.get("data-rate") or 0)))
        if label.startswith("量"):
            weights = opts
        elif label.startswith("状態"):
            states = opts
    w_best = None
    for txt, rate in weights:
        m = WEIGHT_PATTERN.search(txt)
        if m:
            g = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
            if w_best is None or g < w_best[0]:
                w_best = (g, rate)
    bean_rate = 0
    for txt, rate in states:
        if "豆" in txt:
            bean_rate = rate
            break
    if not w_best:
        return None
    return w_best[0], base_price + w_best[1] + bean_rate


def build_record(slug: str) -> dict | None:
    url = f"{BASE_URL}/i/{slug}"
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")
    ld = None
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(sc.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            ld = d
            break
    if not ld:
        return None
    title = re.sub(r"\s+", " ", ld.get("name") or "").strip()
    if any(k in title for k in EXCLUDE_TITLE):
        return None
    offers = ld.get("offers") or {}
    base_price = int(offers.get("price"))
    available = "InStock" in (offers.get("availability") or "")

    item_no = re.search(r"name=['\"]itemNo['\"] value=['\"](\d+)", html) or re.search(r"name='itemNo' value='(\d+)'", html)
    weight, price = None, base_price
    if item_no:
        form = get(f"{BASE_URL}/api/front/template/formSelection?package_item_no=&item_no={item_no.group(1)}")
        picked = pick_variant(form, base_price)
        if picked:
            weight, price = picked
    if weight is None:
        return None

    for x in soup.select("script,style"):
        x.decompose()
    text = soup.get_text("\n", strip=True)
    rm = ROAST_PATTERN.search(text)
    roast_level = rm.group(1) if rm else None
    flavor = None
    desc = ld.get("description")
    body_m = re.search(re.escape(title) + r"\n" + re.escape(title) + r"\n(.+?)\n焙煎度", text, re.S)
    if body_m:
        flavor = re.sub(r"\s+", " ", body_m.group(1)).strip()[:400]
    crumbs = text[: text.find("■")] if "■" in text else ""
    is_blend = "ブレンド" in title or "オリジナルブレンド" in crumbs

    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if not c and title.startswith("タイ "):
                c = "タイ"
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

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
        "flavor_notes": flavor or desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for slug in list_slugs():
        rec = build_record(slug)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_kadokawacraft.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kadokawacraft.json に出力しました")


if __name__ == "__main__":
    main()
