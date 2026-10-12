# -*- coding: utf-8 -*-
"""
scrape_horoniga.py

珈琲工房 ほろにが(horoniga.com)の自家焙煎コーヒー豆の商品情報を取得する。栃木県小山市。
独自カート(cart/cgi/cart.cgi)の静的HTML。商品一覧 cart/Straight_Index.html /
cart/Blend_Index.html から商品ページ(cart/Straight/*.html, cart/Blend/*.html)を辿り、
各ページの「100ｇ / ○○円(税込)」を代表価格(最小重量100g)として採用する。
2026-10-12確認(2026-09-25に価格改定済み)。robots.txt は存在しない(404)。

【除外】
- 水出しアイスバッグ、ドリップバッグ、ギフト、お試し/お任せセット、器具(別ページのため辿らない)
- ブレンドページ内の「3袋/4袋セット」価格(100gのみ採用)
- 「俺の浅煎り」VOL.1(深煎りは掲載)以外の旧ブラインド企画(VOL.2〜5・準備中ページ。産地非公開・過去企画)
  VOL.6(現行)は産地非公開のためorigin=None、ストレート扱いで掲載。
【在庫】ページ内に「完売いたしました」があれば品切れ。
"""
import re
import time
import json

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "珈琲工房 ほろにが",
    "url": "http://www.horoniga.com/",
    "platform": "独自カート(静的HTML、cart.cgi)",
    "address": "栃木県小山市卒島824",
    "prefecture": "栃木県",
    "robots_txt_status": "robots.txtなし(404、2026-10-12確認)",
}
BASE = "http://www.horoniga.com/cart/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 1
# 過去のブラインド企画・準備中・解説のみ(購入フォーム無し)のページ
SKIP_PAGES = {
    "Straight/LightRoast.html", "Straight/LightRoast_VOL2.html", "Straight/LightRoast_VOL3_Answer.html",
    "Straight/LightRoast_VOL4.html", "Straight/LightRoast_VOL5.html",
}
COUNTRIES = ["コロンビア", "ペルー", "インドネシア", "ケニア", "エチオピア", "ホンジュラス", "コスタリカ", "ルワンダ",
             "グアテマラ", "ブラジル", "タンザニア"]
ROAST_MAP = [("ファイン", "中煎り〜中深煎り（ファインロースト）"), ("深深煎り", "深深煎り"), ("深煎り", "深煎り"),
             ("浅煎り", "浅煎り")]


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_pages():
    pages = []
    for idx in ("Straight_Index", "Blend_Index"):
        s = BeautifulSoup(get(BASE + idx + ".html"), "html.parser")
        for a in s.find_all("a", href=True):
            h = a["href"]
            if h.startswith(("Straight/", "Blend/")) and h not in pages and h not in SKIP_PAGES:
                pages.append(h)
        time.sleep(DELAY)
    return pages


def roast_of(label):
    for k, v in ROAST_MAP:
        if k in label:
            return v
    return None


def parse_page(path):
    html = get(BASE + path)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    title = soup.title.get_text(strip=True).rsplit("-珈琲工房", 1)[0]
    is_blend = path.startswith("Blend/")
    name = re.sub(r"（[^）]*煎り[^）]*）", "", title).replace("_", " ").strip()
    if name.startswith("俺の"):
        name = name.replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    m = re.search(r"100ｇ\s*/\s*([\d,]+)円", text)
    price = int(m.group(1).replace(",", "")) if m else None
    out = "完売いたしました" in text
    body = text[text.find("お問合わせ"):]

    roast = None
    if is_blend:
        mid = soup.select_one("td.Midasi")
        mh = re.search(r"[(（]([^)）]*)[)）]", mid.get_text(" ", strip=True)) if mid else None
        roast = roast_of(mh.group(1)) if mh else roast_of(title)
    else:
        roast = roast_of(title)

    components = []
    mc = re.search(r"(?:使用の豆|生産国)\n((?:・[^\n]+\n?)+)", body)
    if mc:
        components = [c.strip("・ ").split("/")[0].strip() for c in mc.group(1).split("\n") if c.strip()]
        components = [c for c in components if c and c != "Secret"]

    origin = None
    if not is_blend and not name.startswith(("俺の", "VOL")):
        origin = next((c for c in COUNTRIES if name.startswith(c)), None)
    if "VOL.1" in name or "VOL1" in name:
        origin = "ルワンダ"
    blend = is_blend or name.startswith("のー・ブラジル")

    farm = []
    for key in ("生産者", "農園", "所在", "標高", "栽培品種", "品種", "精製", "乾燥"):
        mk = re.search(r"^" + key + r"：(.+)$", body, re.M)
        if mk:
            farm.append("%s：%s" % (key, mk.group(1).strip()))
    flav = []
    for label in ("酸味", "苦味", "香り", "コク", "後味"):
        mf = re.search(r"^" + label + r"\n(?:[★☆]+\n)+([^\n★]+)", body, re.M)
        if mf:
            flav.append("%s：%s" % (label, mf.group(1).strip()))

    parsed = parse_product(name)
    parsed = apply_category_hint_fallback(parsed, name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    elif origin:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name"
    if not parsed["processing_method"]:
        parsed["processing_method"] = detect_processing_method("\n".join(farm))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast,
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": "、".join(farm) or None,
        "flavor_notes": "、".join(flav) or None,
        "blend_components": components if blend else [],
        "price": price,
        "weight_g": 100 if price else None,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": BASE + path,
    }


if __name__ == "__main__":
    records = []
    for p in list_pages():
        records.append(parse_page(p))
        time.sleep(DELAY)
    with open("data_horoniga.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print("[done] %d件" % len(records))
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_hint"],
              r["processing_method"], r["stock_status"], r["blend_components"])
