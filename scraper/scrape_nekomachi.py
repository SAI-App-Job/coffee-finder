# -*- coding: utf-8 -*-
"""
scrape_nekomachi.py

猫町珈琲店(新潟県村上市小町3-9。風呂猫マーケット furonekomarket.ocnk.net 内の
「猫町珈琲店」カテゴリ)の商品情報を取得する。おちゃのこネット(Ocnk)。

【対象商品】猫町珈琲店カテゴリ(/product-list/55)のうち、商品コードが「B-」で始まる
コーヒー豆200g 9点(ストレート6、ブレンド3)。マグカップ・キャニスター缶(C-)は除外。
価格はog/商品メタ(product:price:amount)、産地・精製方法・焙煎度は商品ページの
【生産国】【精製方法】【焙煎(度合)】表記から取得する(ブレンドは原材料名の生豆生産国
のみで焙煎度の表記なし)。在庫切れ表示は一覧・詳細とも見当たらないため販売中として扱う。

robots.txt確認済み(2026-10): GPTBot等のAI系ボットのみDisallow、それ以外は制限なし。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "猫町珈琲店",
    "url": "https://furonekomarket.ocnk.net/product-list/55",
    "platform": "おちゃのこネット(Ocnk、風呂猫マーケット内)",
    "address": "新潟県村上市小町3-9",
    "prefecture": "新潟県",
    "robots_txt_status": "実質許可(2026-10確認。GPTBot等AI系ボットのみ個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://furonekomarket.ocnk.net"
LIST_URL = f"{BASE_URL}/product-list/55"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
SOLDOUT_PATTERN = re.compile(r"在庫切れ|SOLD ?OUT|売り切れ|品切れ|入荷待ち", re.I)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8", "replace")


def list_bean_products() -> list[str]:
    html_text = fetch(LIST_URL)
    soup = BeautifulSoup(html_text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=re.compile(r"/product/\d+$")):
        text = unicodedata.normalize("NFKC", a.get_text(" ", strip=True))
        if re.search(r"\[\s*B-[A-Z]+\s*\]", text) and a["href"] not in urls:
            urls.append(a["href"])
    return urls


def build_record(url: str) -> dict:
    html_text = fetch(url)
    soup = BeautifulSoup(html_text, "html.parser")
    title = unicodedata.normalize("NFKC", soup.select_one('meta[property="og:title"]')["content"])
    name = re.sub(r"\s*\d+\s*g\s*$", "", title).strip()
    name = re.sub(r"\s+", " ", name)
    price_m = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_m["content"])) if price_m else None
    desc_el = soup.select_one("div.item_desc_text")
    desc_text = unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)) if desc_el else ""
    desc_text = re.sub(r"\s+", " ", desc_text)
    weight_m = re.search(r"内容量】?\s*(\d+)\s*g", desc_text) or re.search(r"(\d+)\s*g\s*$", title)
    weight = int(weight_m.group(1)) if weight_m else None
    roast_m = re.search(r"【焙煎(?:度合)?】\s*([^\s(（【]+)", desc_text)
    roast = roast_m.group(1) if roast_m else None
    process_m = re.search(r"【精製方法】\s*(\S+)", desc_text)
    country_m = re.search(r"【生産国】\s*(\S+)", desc_text)
    flavor = re.split(r"【原材料名】|ラベルイラスト", desc_text)[0]
    flavor = re.sub(r"^.*?コーヒー豆のみの販売\s*", "", flavor).strip()[:400] or None
    sold_out = bool(SOLDOUT_PATTERN.search(soup.get_text(" ")))

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        c = detect_country_name(country_m.group(1)) if country_m else None
        c = c or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or (process_m.group(1) if process_m else None),
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    return [build_record(u) for u in list_bean_products()]


def main():
    records = scrape_all_products()
    with open("data_nekomachi.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nekomachi.json に出力しました")


if __name__ == "__main__":
    main()
