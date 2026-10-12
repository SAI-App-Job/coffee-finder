# -*- coding: utf-8 -*-
"""
scrape_allycaffe.py

アリーカフェ(ally-caffe.ocnk.net、石川県金沢市畝田西3-583、自家焙煎珈琲豆)のネットショップの
商品情報を取得する。おちゃのこネット(Ocnk)。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【robots.txtについて】
実データ確認済み(2026-10-12): robots.txtはGPTBot等の特定AIクローラのみDisallow。
User-agent: *への制限は無く実質許可。識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(2026-10-12時点): 「アリーおすすめ珈琲豆」(product-list/1)の17件
(ブレンド8・シングル8・デカフェ1)が焙煎豆の全てで、器具・フィルター・ギフト・モバイルコーヒー
(ドリップ式)・珈琲牛乳の素は対象外。価格は税込表示。
重量は商品名に「100g」とある商品はそれを採用し、名称に重量が無い商品はオプション(袋サイズ)や
説明にも重量の記載が無い限りnull(マンデリン アルール・バダのみ袋サイズ選択肢「100g」から100g)とする。
焙煎度は説明文の「焙煎度：…」から取る(例「深煎り(フルシティーロースト)」→深煎り、
「ハイロースト(中煎り)」→中煎り)。ブレンドは名称に「ブレンド」を含む商品と、配合内容を明記した
「金澤珈琲」とする。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "アリーカフェ",
    "url": "https://ally-caffe.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "石川県金沢市畝田西3-583",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(2026-10-12確認。GPTBot等の特定クローラのみDisallow、User-agent: *への制限なし)",
}

BASE_URL = "https://ally-caffe.ocnk.net"
CATEGORY_ID = "1"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BLEND_PIDS = {"127"}  # 金澤珈琲(配合内容: エチオピア、ブラジル。名称に「ブレンド」が無い)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]\b", re.IGNORECASE)
COARSE_ROAST_PATTERN = re.compile(r"(極深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
ROAST_LINE_PATTERN = re.compile(r"焙\s*煎\s*度\s*[:：]\s*([^\n]+)")
SOLD_OUT_PATTERN = re.compile(r"売り切れ|売切れ|在庫なし|在庫切れ|品切れ|入荷待ち")
ROAST_FALLBACK = {
    "フルシティ": "深煎り", "シティ": "中深煎り", "ハイ": "中煎り", "ミディアム": "中煎り",
    "フレンチ": "極深煎り", "イタリアン": "極深煎り",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cell in BeautifulSoup(fetch_html(f"{BASE_URL}/product-list/{CATEGORY_ID}"), "html.parser").select("li.list_item_cell"):
        a = cell.select_one("a[href*='/product/']")
        name_el = cell.select_one(".goods_name")
        m = re.search(r"/product/(\d+)", a["href"]) if a else None
        if not (m and name_el) or m.group(1) in items:
            continue
        price_el = cell.select_one(".selling_price .figure")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        stock_el = cell.select_one("p.stock")
        stock_text = stock_el.get_text(strip=True) if stock_el else ""
        items[m.group(1)] = {
            "pid": m.group(1),
            "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))).strip(),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "sold_out": "list_item_soldout" in cell.get("class", []) or bool(SOLD_OUT_PATTERN.search(stock_text)),
        }
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    el = soup.select_one("div.item_desc_text")
    text = unicodedata.normalize("NFKC", el.get_text("\n", strip=True)) if el else ""
    opts = [o.get_text(strip=True) for o in soup.select("select option")]
    size_opt = next((o for o in opts if re.fullmatch(r"\d+\s*g", o)), None)
    return {"text": text, "size_option": size_opt}


def pick_roast(text: str) -> tuple[str | None, str | None]:
    m = ROAST_LINE_PATTERN.search(text)
    if not m:
        return None, None
    raw = m.group(1).strip()
    raw = re.split(r"\s{2,}|認証|地域|標高|品種|精製", raw)[0].strip()
    c = COARSE_ROAST_PATTERN.search(raw)
    if c:
        return c.group(1), raw
    for kw, roast in ROAST_FALLBACK.items():
        if kw in raw:
            return roast, raw
    return None, raw


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        if it["price"] is None:
            continue
        detail = fetch_detail(it["pid"])
        text = detail["text"]
        w_m = WEIGHT_PATTERN.search(it["title"])
        weight_g = int(w_m.group(1)) if w_m else (
            int(re.sub(r"\D", "", detail["size_option"])) if detail["size_option"] else None)
        name = re.sub(r"\s+", " ", WEIGHT_PATTERN.sub(" ", it["title"])).strip()
        parsed = parse_product(name)
        if "ブレンド" in name or it["pid"] in BLEND_PIDS:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(name)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["processing_method"] and text:
            m = re.search(r"精製方法\s*[:：]\s*([^\s　]+)", text)
            parsed["processing_method"] = extract_from_description("精製方法：" + m.group(1))["processing_method"] if m else None
        roast, roast_hint = pick_roast(text)
        desc = re.sub(r"\s+", " ", text)[:400] or None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": it["price"],
            "weight_g": weight_g,
            "stock_status": "完売" if it["sold_out"] else "販売中",
            "out_of_stock": it["sold_out"],
            "product_url": f"{BASE_URL}/product/{it['pid']}",
        })
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    with open("data_allycaffe.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_allycaffe.json に出力しました")


if __name__ == "__main__":
    main()
