# -*- coding: utf-8 -*-
"""
scrape_asahicoffee.py

旭珈琲(ASAHICOFFEE、www.asahicoffee.co.jp、大阪市西区南堀江3-12-21、1948年創業の自家焙煎コーヒー店)の
商品情報を取得する。MakeShop(UTF-8、商品ページは /view/item/<商品番号>)。

【対象商品について】
実データ確認済み(2026-10時点): 「コーヒー豆一覧」(view/category/coffee、2ページ)と、
その下位カテゴリ(ブレンド ct5・シングルオリジン ct12・深煎りストレート ct13・スペシャルティ ct14・
アイスコーヒー用 ct15・カフェインレス ct17・今週のお買い得 ct6)の商品を重複を除いて集め、
「グラム」選択肢を持つ豆商品のみを対象とする(約45銘柄)。
次は対象外: ネコポス(クリックポスト)便の袋詰めセット・飲み比べセット・お試しセット、
ドリップバッグ、生豆、紅茶、器具、ギフト、「受注焙煎」の500g単品(同一銘柄の100g商品が別にあるため重複)。
「深煎り〇〇」と「〇〇」のように同じ豆を異なる焙煎度で並べた商品は別商品として扱う。

【価格・重量・在庫】
商品ページのグラム選択肢(100g/200g/300g/500g)の最小重量を重量とし、ページ表示の税込価格
(data-id="makeshop-item-price:1")を代表価格とする。「バリュー・アイスコーヒー」「バリュー・ブレンド」は
500gのみの選択肢のため500gを採用。在庫は商品ページの`soldout--detail`要素に`off`クラスが
付いていれば販売中、付いていなければ品切れとして判定する。
商品名の「≪コーヒーフェアー価格≫」(期間限定の販促表記)は除去する。
ブレンド/ストレートはカテゴリ(ブレンド ct5・アイスコーヒー用 ct15)と商品名の「ブレンド」で判定する。
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
    "name": "旭珈琲",
    "url": "https://www.asahicoffee.co.jp/",
    "platform": "MakeShop",
    "address": "大阪府大阪市西区南堀江3-12-21",
    "prefecture": "大阪府",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.asahicoffee.co.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["coffee", "ct5", "ct12", "ct13", "ct14", "ct15", "ct17", "ct6"]
BLEND_CATEGORIES = {"ct5", "ct15"}
MAX_PAGES = 4
EXCLUDE_KEYWORDS = (
    "クリックポスト", "ネコポス", "セット", "お試し", "ドリップ", "受注焙煎", "生豆", "紅茶", "ギフト", "送料無料",
)
FAIR_TAG_PATTERN = re.compile(r"\s*≪コーヒーフェアー価格≫\s*")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_item_ids() -> dict[str, set[str]]:
    """商品番号 -> 所属カテゴリID集合。"""
    ids: dict[str, set[str]] = {}
    for cat in CATEGORY_IDS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/view/category/{cat}" + ("" if page == 1 else f"?page={page}")
            soup = BeautifulSoup(fetch_html(url), "html.parser")
            main = soup.select_one("section.main-contents-categoryitems")
            found = set(re.findall(r"/view/item/(\d+)", str(main))) if main else set()
            new = [f for f in found if cat not in ids.get(f, set())]
            for f in found:
                ids.setdefault(f, set()).add(cat)
            if not new:
                break
    return ids


def parse_description(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """「商品説明」以降〜「製造元」「送料について」までの本文を返す。(全文, 400字に切った文)。"""
    text = soup.get_text("\n", strip=True)
    i = text.find("商品説明")
    if i < 0:
        return None, None
    body = text[i + len("商品説明"):]
    cuts = [k for k in (body.find("製造元"), body.find("送料について")) if k >= 0]
    if cuts:
        body = body[:min(cuts)]
    body = body.strip()
    return (body or None), (re.sub(r"\s+", " ", body)[:400] or None)


def build_record(pid: str, cats: set[str]) -> dict | None:
    url = f"{BASE_URL}/view/item/{pid}"
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", property="og:title")
    raw = og["content"].split("|")[0] if og and og.get("content") else None
    if not raw:
        return None
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", FAIR_TAG_PATTERN.sub(" ", raw))).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None

    weights = []
    for opt in soup.select("select option"):
        m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", opt.get_text(strip=True)))
        if m:
            weights.append(int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1))
    price_el = soup.select_one("[data-id^='makeshop-item-price:']")
    if not weights or not price_el:
        return None
    pm = re.search(r"[\d,]+", price_el.get_text())
    if not pm:
        return None
    weight = min(weights)
    price = int(pm.group(0).replace(",", ""))

    soldout_m = re.search(r'class="(soldout--detail[^"]*)"', html)
    out_of_stock = bool(soldout_m) and "off" not in soldout_m.group(1).split()

    full_desc, desc = parse_description(soup)
    parsed = parse_product(title)
    if (cats & BLEND_CATEGORIES) or "ブレンド" in title:
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
        if not parsed["origin_country"] and full_desc:
            m = re.search(r"(?:原産国|生産国|産地国?)\s*[:：]\s*([^\n]+)", full_desc)
            c = detect_country_name(m.group(1)) if m else None
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, title)
    if not parsed["processing_method"] and full_desc:
        parsed["processing_method"] = extract_from_description(full_desc)["processing_method"]

    rm = COARSE_ROAST_PATTERN.search(title)
    roast_level = rm.group(1) if rm else ("深煎り" if "ct13" in cats else None)

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
        "flavor_notes": desc,
        "farm_note": None,
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
    for pid, cats in sorted(collect_item_ids().items()):
        rec = build_record(pid, cats)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_asahicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_asahicoffee.json に出力しました")


if __name__ == "__main__":
    main()
