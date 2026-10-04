# -*- coding: utf-8 -*-
"""
scrape_mamekichihimeji.py

珈琲煎舗 豆きち(coffee-mamekichi.net、兵庫県姫路市飾磨区矢倉町1-71、自家焙煎の煎りたてコーヒー販売)の
商品情報を取得する。独自PHPカート(UTF-8)。
※ scrape_mamekichi.py は東京都立川市の別店舗「珈琲豆焙煎工房 まめ吉」のため、slugを分けている。

【対象商品について】
実データ確認済み(2026-10時点): トップページの商品リスト(ブレンド6件=n_order02_bl.php?id=2、
高額商品等・ストレート=n_order02_st.php?id=1、計46件)が対象。全て焙煎豆。
価格表記は「価格(商品名に記載のないものは200g)」で、商品名に(100g)等の記載があるものはその重量、
無ければ200gの価格。容量違いのバリエーションは無く、1商品=1重量・1価格(ブレンドは「¥/200g」)。
焙煎度合は注文時に選べる(中煎り/やや深煎り/深煎り)商品が多く、焙煎度自体は固定ではないため
roast_level/roast_hintは設定しない(注文時選択式)。在庫はページ内の「品切れ」表示で判定する。
商品ページには個別のURLがあり、product_urlはそのURLを使う。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "珈琲煎舗 豆きち",
    "url": "https://coffee-mamekichi.net/",
    "platform": "独自PHPカート",
    "address": "兵庫県姫路市飾磨区矢倉町1-71",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://coffee-mamekichi.net/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LABEL_RE = re.compile(r"^(生産国|生産地|地域|農園名|等\s*級|品\s*種|精\s*選|標高|認\s*証|生産者|備考)[\s：:]+(.+)$")
SKIP_LINES = ("価格", "焙煎度合", "注文数", "品切れ", "個", "中煎り", "やや深煎り", "深煎り", "(注)")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_links() -> list[tuple[str, bool]]:
    soup = fetch(BASE_URL)
    links, seen = [], set()
    for a in soup.select('a[href*="n_order02_"]'):
        href = a["href"].lstrip("./")
        if href in seen:
            continue
        seen.add(href)
        links.append((BASE_URL + href, "n_order02_bl" in href))
    return links


def build_record(url: str, is_blend: bool) -> dict:
    soup = fetch(url)
    for x in soup(["script", "style"]):
        x.decompose()
    lines = [unicodedata.normalize("NFKC", l).strip() for l in soup.get_text("\n", strip=True).split("\n")]
    lines = [l for l in lines if l]
    # 先頭は店名、2行目が商品名。末尾は店舗情報(「珈琲煎舗 豆きち」以降)
    title_raw = lines[1]
    end = next((i for i in range(2, len(lines)) if lines[i].startswith("珈琲煎舗")), len(lines))
    body = lines[2:end]
    sold_out = "品切れ" in body
    price = None
    weight = 200
    for i, ln in enumerate(body):
        if ln.startswith("価格"):
            m = re.search(r"/\s*(\d+)\s*g", ln)
            if m:
                weight = int(m.group(1))
            for nxt in body[i + 1:i + 3]:
                pm = re.match(r"^([\d,]+)円$", nxt)
                if pm:
                    price = int(pm.group(1).replace(",", ""))
                    break
            break
    wm = re.search(r"\((\d+)\s*g\)", title_raw)
    if wm:
        weight = int(wm.group(1))
    country_m = re.match(r"^<([^>]+)>\s*(.*)$", title_raw)
    bracket_country = country_m.group(1) if country_m else None
    name = (country_m.group(2) if country_m else title_raw)
    name = re.sub(r"\s*\(\d+\s*g\)\s*", " ", name).strip()
    name = re.sub(r"\s+", " ", name)
    raw_name = f"{bracket_country} {name}" if bracket_country else name

    labels, desc = {}, []
    for ln in body:
        if ln.startswith(SKIP_LINES) or re.match(r"^\d+円$", ln):
            continue
        m = LABEL_RE.match(ln)
        if m:
            labels[re.sub(r"\s+", "", m.group(1))] = m.group(2).strip()
        elif "\t" not in ln:
            desc.append(ln)

    # 焙煎度を選べない商品は本文冒頭に「浅煎り」「超深煎り」等の1行がある(実データ確認済み)
    roast_hint = None
    if desc and re.fullmatch(r"(?:超|極)?(?:中)?(?:浅|深)煎り|中煎り|やや深煎り", desc[0]):
        roast_hint = desc.pop(0)

    parsed = parse_product(raw_name)
    processing = None
    if is_blend or parsed["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(raw_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, raw_name)
        if not parsed["origin_country"] and labels.get("生産国"):
            c = detect_country_name(labels["生産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and labels.get("精選"):
            processing = normalize_processing_method(labels["精選"])
    farm_bits = [f"{k}: {labels[k]}" for k in ("生産地", "地域", "農園名", "標高", "品種") if labels.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": labels.get("等級") or parsed["grade"],
        "roast_level": None,
        "roast_hint": roast_hint,
        "roast_selectable": "焙煎度合" in body,  # 注文時に焙煎度を選べる商品
        "flavor_notes": " ".join(desc)[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url, is_blend in list_links():
        try:
            records.append(build_record(url, is_blend))
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {url} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamekichihimeji.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekichihimeji.json に出力しました")


if __name__ == "__main__":
    main()
