# -*- coding: utf-8 -*-
"""
scrape_peacecoffee.py

PEACE COFFEE ROASTERS(ピースコーヒー、千葉県茂原市茂原15-5 山田ビル1F、焙煎所・珈琲工房は
千葉県茂原市高師1083-2、peace-coffee.jp。2010年導入の米国製スマートロースターで自家焙煎、
店舗は上記2店)の商品情報を取得する。WordPress + WooCommerce(バリエーション商品)。

【対象商品について】
実データ確認済み(2026-10時点、お知らせの最終更新2026-05-21): カテゴリ「珈琲豆」
(/products/珈琲豆/)の10銘柄(ストレート9・ブレンド1(イタリアンブレンド)、うちデカフェ1)を対象とする。
珈琲グッズ・ギフトは別カテゴリのため対象外。

【価格・重量・在庫について】
各商品詳細ページの `data-product_variations`(WooCommerce標準のバリエーションJSON)から、
挽き方「豆のまま」×サイズ(100g/250g/500g)のバリエーションを読み取り、在庫のある最小サイズの
税込価格を代表とする(全サイズ在庫切れの場合は最小サイズ)。全バリエーションが在庫切れの場合は完売。
商品名の先頭の「※」は除去し、末尾の括弧内の焙煎度(中煎り・深煎り等)を roast_level / roast_hint に反映する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "PEACE COFFEE ROASTERS",
    "url": "https://peace-coffee.jp/",
    "platform": "WordPress + WooCommerce",
    "address": "千葉県茂原市茂原15-5 山田ビル1F",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

LIST_URL = "https://peace-coffee.jp/products/%e7%8f%88%e7%90%b2%e8%b1%86/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_PAREN = re.compile(r"[（(]\s*([^（()）]*煎り)\s*[）)]\s*$")
ORIGIN_OVERRIDES = {"マンデリン": "インドネシア"}


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_product_urls() -> list[str]:
    soup = fetch(LIST_URL)
    urls: list[str] = []
    for a in soup.select("a[href*='/product/']"):
        href = a["href"].split("#")[0]
        if href not in urls:
            urls.append(href)
    return urls


def parse_detail(url: str) -> dict | None:
    soup = fetch(url)
    form = soup.select_one("form.variations_form")
    title_el = soup.select_one("h1") or soup.select_one("title")
    # 商品名: ページの <title> は「商品名 | 商品一覧 | …」
    title = soup.title.get_text(strip=True).split("|")[0].strip() if soup.title else ""
    if not title and title_el:
        title = title_el.get_text(strip=True)
    if not form or not form.get("data-product_variations"):
        return None
    variations = json.loads(html.unescape(form["data-product_variations"]))
    beans = []
    for v in variations:
        attrs = v.get("attributes", {})
        grind = requests.utils.unquote(attrs.get("attribute_pa_grind", ""))
        if grind not in ("豆のまま", ""):
            continue
        size = attrs.get("attribute_pa_size", "")
        m = re.match(r"(\d+)g", size)
        if not m:
            continue
        beans.append({
            "weight": int(m.group(1)),
            "price": int(v.get("display_price")),
            "in_stock": bool(v.get("is_in_stock")) and bool(v.get("is_purchasable", True)),
        })
    if not beans:
        return None
    in_stock = [b for b in beans if b["in_stock"]]
    rep = min(in_stock or beans, key=lambda b: b["weight"])

    notes = None
    dd = soup.select_one("dd.c-detail-data__desc")
    if dd:
        notes = " ".join(dd.get_text(" ", strip=True).split()) or None
    return {
        "title": title,
        "url": url,
        "price": rep["price"],
        "weight": rep["weight"],
        "out": not in_stock,
        "notes": notes,
    }


def build_record(d: dict) -> dict:
    name = d["title"].lstrip("※").strip()
    name = re.sub(r"[\s　]+", " ", name)
    rm = ROAST_PAREN.search(name)
    roast_hint = rm.group(1) if rm else None
    roast_level = None
    if roast_hint:
        roast_level = {"極深煎り": "イタリアンロースト"}.get(roast_hint, roast_hint)

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            head = name.split(" ")[0]
            c = ORIGIN_OVERRIDES.get(head) or detect_country_name(head)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": d["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": "完売" if d["out"] else "販売中",
        "out_of_stock": d["out"],
        "product_url": d["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            d = parse_detail(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {url} ({e})")
            continue
        if d:
            records.append(build_record(d))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_peacecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_peacecoffee.json に出力しました")


if __name__ == "__main__":
    main()
