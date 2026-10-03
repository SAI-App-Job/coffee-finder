# -*- coding: utf-8 -*-
"""
scrape_mamenoyuu.py

珈琲豆 優(coffeemame-you.jp、東京都豊島区要町1-13-9 メゾン・デュ・シェーヌ1F、
運営は(有)豆香房。要町駅徒歩3分。コーヒーマイスターの店主が50種類以上の生豆から、
ご注文を受けてから焙煎する自家焙煎店、単独1店舗)の商品情報を取得する。
静的HTML+外部カート(cart.ec-sites.jp)。

【ページ構造について】
実データ確認済み(2026-10時点): 「インターネットで購入する」ページ(/web.html)に全商品が
`div.wrap-box`単位で並び、`h3.title`に商品名、`h4.pr`に「1,490円/200g」(売り切れは
「【売り切れ】」付き)、`p.memo`に紹介文、`a[href^="cart/"]`に商品ページ(cart/A2.html等)が
載っている。各商品は200g/300g/400g/500gの重量別価格だが、一覧は最小の200g価格のため
200gを代表重量・価格とする。焙煎度は注文時に選択(中浅煎り〜イタリアン・店長おまかせ)の
ため設定しない。

【対象商品について】
ブラジル〜ブレンド(優/コクマロ/ビター等)・デカフェ(やすらぎ)の焙煎豆76銘柄を対象とする。
「インターネット限定 水出しコーヒーパック」(K1)と「スペシャルティコーヒー 飲み比べセット」
(L1)は豆単品ではないため除外する。産地欄(生産地)は大陸名のため使わず、商品名から判定する。
"""

import json
import re
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "珈琲豆 優",
    "url": "https://www.coffeemame-you.jp/",
    "platform": "静的HTML+外部カート(ec-sites)",
    "address": "東京都豊島区要町1-13-9 メゾン・デュ・シェーヌ1F",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.coffeemame-you.jp/"
PAGE_URL = BASE_URL + "web.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_CODES = {"K1", "L1"}  # 水出しコーヒーパック・飲み比べセット
PRICE_PATTERN = re.compile(r"([\d,]+)円\s*/?\s*(\d+)\s*g")

# 商品名に国名が無く、地域名・銘柄名から産地が一意に定まるもの
NAME_COUNTRY_HINTS = {
    "ニューギニア": "パプアニューギニア",
}


def build_record(box) -> dict | None:
    title_el = box.select_one("h3.title")
    price_el = box.select_one("h4.pr")
    link = box.select_one('a[href^="cart/"]')
    if not (title_el and price_el and link):
        return None
    code = re.search(r"cart/([A-Za-z]+\d+)\.html", link["href"])
    if not code or code.group(1) in EXCLUDE_CODES:
        return None
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title_el.get_text(" ", strip=True)))
    price_text = unicodedata.normalize("NFKC", re.sub(r"\s+", "", price_el.get_text()))
    pm = PRICE_PATTERN.search(price_text)
    if not pm:
        return None
    price = int(pm.group(1).replace(",", ""))
    weight_g = int(pm.group(2))
    out_of_stock = "売り切れ" in price_text or "売切" in price_text

    memo_el = box.select_one("p.memo")
    memo = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", memo_el.get_text(" ", strip=True))) if memo_el else None

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            hint = next((v for k, v in NAME_COUNTRY_HINTS.items() if k in name), None)
            detected = hint or detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(name + " " + (memo or "")),
        "grade": parsed["grade"],
        # 「ハイチ」が焙煎度キーワード「ハイ」に誤一致するため、国名を除いた名称で判定する
        "roast_level": parse_product(name.replace("ハイチ", ""))["roast_level"],
        "roast_hint": "注文焙煎(焙煎度は注文時に選択)",
        "flavor_notes": memo,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": urljoin(BASE_URL, link["href"]),
    }


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    records = []
    seen = set()
    for box in soup.select("div.wrap-box"):
        rec = build_record(box)
        if rec is None or rec["product_url"] in seen:
            continue
        seen.add(rec["product_url"])
        records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamenoyuu.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamenoyuu.json に出力しました")


if __name__ == "__main__":
    main()
