# -*- coding: utf-8 -*-
"""
scrape_hannacoffee.py

阪奈珈琲豆店(HANNA COFFEE R*、hannacoffee.ocnk.net、大東市野崎4-7-31)の商品情報を取得する。おちゃのこネット(Ocnk)。

【対象商品について】
実データ確認済み(2026-10時点): 「焙煎豆(ストレート)」(product-list/1)と「焙煎豆(ハウスブレンド)」(product-list/6)の商品。
各銘柄が「【100g】」と「【36g】」(小分けパック)の別商品で並ぶため、【36g】は試飲用の小分けパックのため、通常の販売単位である【100g】を代表とする(100gがなければ最小重量)。
ドリップバッグ・古本・器具カテゴリは対象外。
自家焙煎の焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とし、ドリップバッグ・
セット/ギフト・定期便・生豆・器具・飲料等は除外する。
同一銘柄が重量違いの別商品として並ぶため、銘柄ごとに最小重量の商品を代表として採用する
(価格は一覧ページの税込販売価格、在庫は一覧の品切れ表示(list_item_soldout)で判定し、
説明文に「終売とさせて」「販売を停止」とある場合はそれぞれ終売・一時的に品切れとする)。
住所は特定商取引法ページ(/info)で確認済み。
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
    "name": "阪奈珈琲豆店(HANNA COFFEE R*)",
    "url": "https://hannacoffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "大阪府大東市野崎4-7-31",
    "prefecture": "大阪府",
    "robots_txt_status": "未確認(Ocnk標準構成)",
}

BASE_URL = "https://hannacoffee.ocnk.net"
CATEGORIES = [("1", "single"), ("6", "blend")]  # (カテゴリID, 区分)。区分は "single" または "blend"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 15
DESC_STOP_PATTERN = re.compile(r"＿{5,}")
NOISE_HEADINGS = ("お知らせ", "おことわり", "注文焙煎", "オーダー焙煎", "お支払い", "保存方法", "賞味期限")
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")

NAME_PATTERN = re.compile(r"^【(\d+)g】(.+)$")


def split_name(name: str) -> dict | None:
    """「【100g】銘柄名」「【36g】銘柄名」形式の商品を対象とする。"""
    m = NAME_PATTERN.match(unicodedata.normalize("NFKC", name))
    if not m:
        return None
    base = re.sub(r"\s+", " ", m.group(2)).strip()
    return {"base": base, "weight": int(m.group(1)), "key": base.replace(" ", "")}



def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/product-list/{cat_id}" + ("" if page == 1 else f"?page={page}")
            soup = BeautifulSoup(fetch_html(url), "html.parser")
            new = 0
            for cell in soup.select("li.list_item_cell"):
                a = cell.select_one("a.item_data_link")
                name_el = cell.select_one(".goods_name")
                if not (a and name_el):
                    continue
                m = re.search(r"/product/(\d+)", a["href"])
                if not m or m.group(1) in items:
                    continue
                new += 1
                price_el = cell.select_one(".selling_price .figure")
                pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
                items[m.group(1)] = {
                    "pid": m.group(1),
                    "name": re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "sold_out": "list_item_soldout" in cell.get("class", []),
                    "group": group,
                }
            if new == 0:
                break
    return list(items.values())


def clean_description(text: str) -> str:
    """商品説明から店舗のお知らせ・注文案内・保存方法などの定型セクション(「■」見出し)を除く。"""
    kept = []
    skipping = False
    for line in text.split("\n"):
        if line.startswith("■"):
            skipping = any(w in line for w in NOISE_HEADINGS)
            if skipping or line.startswith("■この商品は"):
                continue
            line = line.lstrip("■ ")
        elif skipping:
            continue
        if line.strip() == "説明":
            continue
        kept.append(line.replace("\\", "").replace("//", "").strip())
    return "\n".join(l for l in kept if l).strip()


def fetch_description(pid: str) -> tuple[str | None, str | None]:
    """商品詳細ページの説明文(div.item_desc_text)を返す。(説明全文, 400字に切った文)。"""
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    el = soup.select_one("div.item_desc_text")
    if not el:
        return None, None
    text = el.get_text("\n", strip=True)
    m = DESC_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()]
    text = clean_description(text)
    return (text or None), (re.sub(r"\s+", " ", text)[:400] or None)


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[int, dict, dict]] = {}
    for item in list_items():
        parts = split_name(item["name"])
        if not parts or item["price"] is None:
            continue
        key = parts["key"]
        cand = (parts["weight"], item, parts)
        cur = best.get(key)
        # 100gを優先(36gは試飲用の小分けパック)。なければ最小重量。同重量なら在庫のある方を優先
        def rank(w):
            return (0 if w == 100 else 1, w)
        if (cur is None or rank(cand[0]) < rank(cur[0])
                or (cand[0] == cur[0] and cur[1]["sold_out"] and not item["sold_out"])):
            best[key] = cand

    records = []
    for weight, item, parts in best.values():
        base = parts["base"]
        full_desc, desc = fetch_description(item["pid"])
        parsed = parse_product(base)
        is_blend = item["group"] == "blend" or "ブレンド" in base
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(base)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"] and full_desc:
                m = re.search(r"(?:生産国|産地国?|原産国)\s*[:：]\s*([^\n]+)", full_desc)
                c = detect_country_name(m.group(1)) if m else None
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, base)
        if not parsed["processing_method"] and full_desc:
            parsed["processing_method"] = extract_from_description(full_desc)["processing_method"]

        status = "完売" if item["sold_out"] else "販売中"
        if status == "販売中" and full_desc:
            if "終売とさせて" in full_desc:
                status = "終売"
            elif "販売を停止" in full_desc:
                status = "一時的に品切れ"
        rm = COARSE_ROAST_PATTERN.search(unicodedata.normalize("NFKC", base))
        roast_level = rm.group(1) if rm else None
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
    with open("data_hannacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hannacoffee.json に出力しました")


if __name__ == "__main__":
    main()
