# -*- coding: utf-8 -*-
"""
scrape_honeycoffee.py

ハニー珈琲(www.honeycoffee.jp、福岡県福岡市博多区那珂6-1-37の本店ショップ&焙煎工場)の
商品情報を取得する。MakeShop(UTF-8、商品ページは /view/item/<商品番号>)。

【対象商品について】
実データ確認済み(2026-10時点): 「すべてのコーヒー豆」(view/category/all、2ページ、34商品)を
起点に、同一銘柄が重量違い(100g/200g/600g/1kg)の別商品として並ぶ構成のため、銘柄ごとに
最小重量(100g)の商品を代表とする。ゴールドラベル(Brazil Cup of Excellence 8,640円)、
30周年限定のゲイシャ(100g 29,700円)など高額品も対象に含める。
次は対象外: 定期便、セット(ゴールデンセット等)、コーヒーバッグ(ドリップ相当)、
アイスコーヒー(水出しパック)、カフェオレベース、ギフト、器具、書籍・雑貨。
「がぶ飲み!」の600g/1kgは同一銘柄の100g商品が別にあるため対象外。

【価格・重量・在庫】
重量は商品名末尾の「100g」等から取得し(ページ内に購入オプションとして重量選択は無い)、
価格は商品ページの税込価格(data-id="makeshop-item-price:1")。在庫は商品ページに
「カートに入れる」ボタンがあるかで判定する。
ブレンド判定はカテゴリ(view/category/blend)と商品名の「ブレンド」「朝霧カフェ」で行う。
産地・精製方法・焙煎度は商品ページの【Profile】欄(原産国/精製方法)と商品名から取得する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "ハニー珈琲",
    "url": "https://www.honeycoffee.jp/",
    "platform": "MakeShop",
    "address": "福岡県福岡市博多区那珂6-1-37",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.honeycoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 6
EXCLUDE_KEYWORDS = (
    "定期便", "セット", "がぶ飲み", "コーヒーバッグ", "水出し", "カフェオレベース", "ギフト", "トート", "コースター", "巾着", "淹れ方",
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
NAME_TRAIL_PATTERN = re.compile(r"\s*(?:\d+\s*(?:kg|g)(?:\s*\(.*?\))?)\s*$", re.I)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_ids(cat: str) -> list[str]:
    ids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}/view/category/{cat}" + ("" if page == 1 else f"?page={page}")
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        ul = soup.select_one("ul.product_lists")
        if not ul:
            break
        new = []
        for a in ul.select("a[href*='/view/item/']"):
            i = re.search(r"/view/item/(\d+)", a["href"]).group(1)
            if i not in ids:
                ids.append(i)
                new.append(i)
        if not new:
            break
    return ids


def parse_item(pid: str, blend_ids: set[str]) -> dict | None:
    url = f"{BASE_URL}/view/item/{pid}"
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]

    price_el = soup.select_one("[data-id^='makeshop-item-price:']")
    if not price_el:
        return None
    pm = re.search(r"[\d,]+", price_el.get_text())
    if not pm:
        return None
    price = int(pm.group(0).replace(",", ""))
    # ページ内で価格表示の直前の行に商品名が表示される
    price_txt = price_el.get_text(strip=True)
    idx = next((k for k, l in enumerate(lines) if l == price_txt and k > 0), None)
    if idx is None:
        return None
    raw_title = lines[idx - 1]
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw_title)).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None

    wm = list(WEIGHT_PATTERN.finditer(title))
    if not wm:
        return None
    # 「200g (100g×2袋)」は先頭の200gを重量とする
    m = wm[0]
    weight = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)

    # 在庫: カートボタンの有無
    out_of_stock = "カートに入れる" not in lines

    # 説明: 価格表示(円(税込))以降〜次の商品名の再掲まで
    desc_lines = []
    try:
        start = lines.index("円（税込）", idx) + 1
    except ValueError:
        start = idx + 2
    for l in lines[start:]:
        if l == raw_title or l.startswith("個数"):
            break
        desc_lines.append(l)
    full_desc = "\n".join(desc_lines)
    profile = {}
    for l in desc_lines:
        pmm = re.match(r"(原産国|地域|標高|品種|精製方法|焙煎度)\s*[:：]\s*(.+)", l)
        if pmm:
            profile[pmm.group(1)] = pmm.group(2).strip()
    taste = None
    tm = re.search(r"【テイストコメント】\n(.+?)(?:\n【|$)", full_desc, re.S)
    if tm:
        taste = tm.group(1).strip()
    intro = None
    im = re.search(r"【(?:商品のご紹介|コーヒーの味わいのご紹介)】\n(.+?)(?:\n【|$)", full_desc, re.S)
    if im:
        intro = im.group(1).strip()
    desc_src = taste or intro or re.sub(r"【.*?】\n?", "", full_desc)
    head, _, rest = desc_src.partition("\n")
    if head.startswith("《") and head.endswith("》") and rest:
        desc_src = rest
    flavor_notes = re.sub(r"\s+", " ", desc_src)[:400] or None

    parsed = parse_product(title)
    if pid in blend_ids or "ブレンド" in title or title.startswith("朝霧カフェ"):
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and profile.get("原産国"):
            c = detect_country_name(profile["原産国"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, title)
    if not parsed["processing_method"] and profile.get("精製方法"):
        parsed["processing_method"] = extract_from_description("精製方法：" + profile["精製方法"])["processing_method"]

    rm = (COARSE_ROAST_PATTERN.search(title)
          or COARSE_ROAST_PATTERN.search(profile.get("焙煎度", ""))
          or (COARSE_ROAST_PATTERN.search(taste) if taste else None)
          or (COARSE_ROAST_PATTERN.search(intro) if intro else None))
    if not rm and parsed["category"] == "ブレンド":
        rm = COARSE_ROAST_PATTERN.search(full_desc[:800])
    roast_level = rm.group(1) if rm else parsed["roast_level"]

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
        "flavor_notes": flavor_notes,
        "farm_note": profile.get("地域"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def base_name(title: str) -> str:
    return NAME_TRAIL_PATTERN.sub("", title).strip()


def scrape_all_products() -> list[dict]:
    ids = collect_ids("all")
    blend_ids = set(collect_ids("blend"))
    items = []
    for pid in ids:
        rec = parse_item(pid, blend_ids)
        if rec:
            items.append(rec)
    # 同一銘柄の重量違いは最小重量を代表にする
    best: dict[str, dict] = {}
    for rec in items:
        key = base_name(rec["raw_name"])
        if key not in best or rec["weight_g"] < best[key]["weight_g"]:
            best[key] = rec
    return list(best.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_honeycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_honeycoffee.json に出力しました")


if __name__ == "__main__":
    main()
