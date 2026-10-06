# -*- coding: utf-8 -*-
"""
scrape_iwaicoffee.py

いわい珈琲(www.iwaicoffee.com、北海道札幌市豊平区月寒東1条6丁目1-20の月寒店と
北区あいの里店の2店舗、スペシャルティコーヒーの自家焙煎・通販)の商品情報を取得する。
おちゃのこネット(Ocnk)。

【住所について】
特定商取引法ページ(/info)は所在地等が画像表示のため文字では取得できない。会社案内
(https://www.iwaicoffee.com/page/1)で実データ確認済み(2026-10時点): 「いわい珈琲 月寒店
札幌市豊平区月寒東一条六丁目1番20号」「あいの里店 札幌市北区あいの里3-4-1-5」。
月寒店の住所を採用する。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(/product-list?page=N)のうち、
「銘柄名【100g】」のように重量が商品名末尾に付く焙煎豆(シングルオリジン・ブレンド・
デカフェ。「ごきげん/やすらぎコーヒー」は粉のみの商品だが焙煎したコーヒーのため対象)。
重量違い(100g/200g/500g/1kg)が別商品として並ぶため、銘柄ごとに最小重量の商品を代表と
する。ドリップパック・コーヒーバッグ・セット・ギフト・定期購入・アイスコーヒー・ゼリー・
器具・ふるさと納税などは名称または重量表記の有無で除外する。

【価格について】
販売価格は「税別」表示で、一覧に「(税込: ○○円)」が併記されている。税込価格を採用する。
在庫は一覧の品切れ表示(list_item_soldout)・SOLD OUT表記で判定する(2026-10時点で品切れは無し)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "いわい珈琲",
    "url": "https://www.iwaicoffee.com/",
    "platform": "おちゃのこネット",
    "address": "北海道札幌市豊平区月寒東1条6丁目1-20",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(Ocnk標準構成)",
}

BASE_URL = "https://www.iwaicoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 10
DESC_STOP_PATTERN = re.compile(r"＿{5,}")
COARSE_ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
NAME_ROAST_PATTERN = re.compile(r"(?<=[ァ-ヴー])(中深|中浅|浅|中|深)(?=\s|$)")
ROAST_FROM_SHORT = {"中深": "中深煎り", "中浅": "中浅煎り", "浅": "浅煎り", "中": "中煎り", "深": "深煎り"}
NAME_PATTERN = re.compile(r"^(.+?)\s*[【(]\s*(\d+(?:\.\d+)?)\s*(kg|g)\s*[】)]\s*(.*)$", re.I)
EXCLUDE_WORDS = ("セット", "ギフト", "定期", "ドリップ", "バッグ", "ゼリー", "アイスコーヒー",
                 "お水de", "フィルター", "クリックポスト", "ポストカード", "ふるさと納税")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def split_name(name: str) -> dict | None:
    """「銘柄名【100g】」形式(重量が末尾の括弧内)の商品を対象とする。"""
    n = unicodedata.normalize("NFKC", name)
    if any(w in n for w in EXCLUDE_WORDS):
        return None
    m = NAME_PATTERN.match(n)
    if not m:
        return None
    base = re.sub(r"\s+", " ", (m.group(1) + " " + m.group(4)).replace("★", "")).strip()
    weight = int(float(m.group(2)) * (1000 if m.group(3).lower() == "kg" else 1))
    return {"base": base, "weight": weight, "key": base.replace(" ", "")}


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}/product-list" + ("" if page == 1 else f"?page={page}")
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        new = 0
        for cell in soup.select("li.list_item_cell"):
            a = cell.select_one("a.list_item_link")
            name_el = cell.select_one(".goods_name")
            if not (a and name_el):
                continue
            m = re.search(r"/product/(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_el = cell.select_one(".tax_incl_price .figure")
            pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
            sold_out = ("list_item_soldout" in cell.get("class", [])
                        or bool(re.search(r"SOLD\s*OUT|品切れ|売り切れ", cell.get_text(" ", strip=True), re.I)))
            items[m.group(1)] = {
                "pid": m.group(1),
                "name": re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": sold_out,
            }
        if new == 0:
            break
    return list(items.values())


def fetch_description(pid: str) -> str | None:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    el = soup.select_one("div.item_desc_text")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    m = DESC_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()]
    return text.strip() or None


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[int, dict, dict]] = {}
    for item in list_items():
        parts = split_name(item["name"])
        if not parts or item["price"] is None:
            continue
        key = parts["key"]
        cand = (parts["weight"], item, parts)
        cur = best.get(key)
        if (cur is None or cand[0] < cur[0]
                or (cand[0] == cur[0] and cur[1]["sold_out"] and not item["sold_out"])):
            best[key] = cand

    records = []
    for weight, item, parts in best.values():
        base = parts["base"]
        desc_full = fetch_description(item["pid"])
        desc = re.sub(r"\s+", " ", desc_full)[:400] if desc_full else None
        parsed = parse_product(base)
        if "ブレンド" in base:
            is_blend = True
        else:
            c = detect_country_name(base)
            if c and not parsed["origin_country"]:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
            # 産地名が無い名称(岩井の深煎・CAFE 4・ごきげんコーヒー等)は店独自のブレンド
            is_blend = not parsed["origin_country"]
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            parsed = apply_category_hint_fallback(parsed, base)
            if not parsed["processing_method"] and desc_full:
                # 説明文に「生産処理はナチュラル」等の記載がある単一銘柄のみ補完
                # (「スマトラ式ではなく、パルプドナチュラル」のような否定表現は否定側を除く)
                pm = re.search(r"生産処理は([^。\n]*)", desc_full)
                if pm:
                    seg = re.sub(r".*ではなく[、,]?", "", pm.group(1))
                    parsed["processing_method"] = detect_processing_method(seg)

        roast_level = None
        m = COARSE_ROAST_PATTERN.search(base)
        if m:
            roast_level = m.group(1)
        else:
            m = NAME_ROAST_PATTERN.search(base)
            if m:
                roast_level = ROAST_FROM_SHORT[m.group(1)]
            elif desc_full:
                m = COARSE_ROAST_PATTERN.search(desc_full)
                if m:
                    roast_level = m.group(1)

        status = "完売" if item["sold_out"] else "販売中"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_level,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": status,
            "out_of_stock": status != "販売中",
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_iwaicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iwaicoffee.json に出力しました")


if __name__ == "__main__":
    main()
