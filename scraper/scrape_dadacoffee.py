# -*- coding: utf-8 -*-
"""
scrape_dadacoffee.py

陀々 DADA(dadacoffee.com、神奈川県相模原市中央区矢部3-18-1の矢部店と、相模大野5-25-43の
相模大野店の2店。自家焙煎珈琲豆専門店。電話・メールで地方発送)の商品情報を取得する。
1ページ構成の静的HTMLで、「今月のおすすめ」表と、「ストレート豆」「ブレンド豆」の表
(香り・酸味・甘味・苦味・コクの5段階評価と「単価(100gあたり)」)に商品が並ぶ。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。サイトに「10月2日(金)は矢部店を臨時休業」の告知があり現行。

【対象商品について】
実データ確認済み(2026-10時点): ストレート13・ブレンド3・今月のおすすめ2(うちブレンド1)の
計18件。HTML内でコメントアウトされている行(アンデスマウンテン等)は取得しない。
単価は「100gあたり」と明記されているため代表重量は100g(今月のおすすめ欄には「ご注文は
200g以上から承ります」とあるが、価格表記は同じ100gあたりの単価として扱う)。
ブレンド豆の名称(「アイス」「フレンチ」)は括弧内の配合国を含めて raw_name とし、
カテゴリはブレンド固定、産地はNone。商品はすべて同一ページのため product_url は
商品名の「#フラグメント」で一意化する。住所は先頭の矢部店を採用。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "陀々 DADA",
    "url": "https://dadacoffee.com/",
    "platform": "静的HTML(電話・メール注文)",
    "address": "神奈川県相模原市中央区矢部3-18-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://dadacoffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
PRICE_PATTERN = re.compile(r"[￥¥]\s*([\d,]+)")

# 商品名・英語名から国名を判別できないもの(表記ゆれ)
ORIGIN_OVERRIDES = {
    "印度珈琲": "インド",
    "東チモール": "東ティモール",
}


def fetch_soup() -> BeautifulSoup:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def row_name(th) -> tuple[str, str | None]:
    """th内の日本語名と英語名(<em>)を返す。"""
    em = th.find("em")
    en = re.sub(r"\s+", " ", em.get_text(" ", strip=True)) if em else None
    if em:
        em.extract()
    jp = re.sub(r"\s+", " ", th.get_text(" ", strip=True)).strip()
    return jp, en


def build_record(name_jp: str, name_en: str | None, price: int, is_blend: bool, note: str | None = None) -> dict:
    if is_blend:
        raw_name = f"{name_jp}{name_en}" if name_en else name_jp  # 例: アイス（ブラジル・コロンビア）
    else:
        raw_name = f"{name_jp} {name_en}" if name_en else name_jp
    parsed = parse_product(raw_name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = ORIGIN_OVERRIDES.get(name_jp)
        detected = override or detect_country_name(raw_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, raw_name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": None,
        "flavor_notes": note,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{PAGE_URL}#{quote(raw_name)}",  # 全商品が同一ページのため一意なフラグメントを付ける
    }


def rating_note(tds) -> str | None:
    labels = ("香り", "酸味", "甘味", "苦味", "コク")
    vals = [td.get_text(strip=True) for td in tds]
    if len(vals) == 5 and all(v.isdigit() for v in vals):
        return " ".join(f"{l}{v}" for l, v in zip(labels, vals)) + "(5段階)"
    return None


def scrape_all_products() -> list[dict]:
    soup = fetch_soup()
    records = []

    # 今月のおすすめ(表 id="sale")
    sale = soup.find("table", id="sale")
    if sale:
        for tr in sale.find_all("tr"):
            th, td = tr.find("th"), tr.find("td", class_="price")
            if not th or not td:
                continue
            m = PRICE_PATTERN.search(td.get_text())
            if not m:
                continue
            name_jp, _ = row_name(th)
            is_blend = "ブレンド" in name_jp
            label = name_jp if is_blend else f"{name_jp}(今月のおすすめ)"
            records.append(build_record(label, None, int(m.group(1).replace(",", "")), is_blend,
                                        "今月のおすすめ(ご注文は200g以上から)"))

    # ストレート豆・ブレンド豆
    for h3 in soup.find_all("h3"):
        kind = h3.get_text(strip=True)
        if kind not in ("ストレート豆", "ブレンド豆"):
            continue
        table = h3.find_next("table", class_="list")
        for tr in table.find_all("tr"):
            th = tr.find("th")
            price_td = tr.find("td", class_="price")
            if not th or not price_td or not th.get_text(strip=True):
                continue
            m = PRICE_PATTERN.search(price_td.get_text())
            if not m:
                continue
            tds = [td for td in tr.find_all("td") if "price" not in (td.get("class") or [])]
            name_jp, name_en = row_name(th)
            records.append(build_record(name_jp, name_en, int(m.group(1).replace(",", "")),
                                        kind == "ブレンド豆", rating_note(tds)))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_dadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dadacoffee.json に出力しました")


if __name__ == "__main__":
    main()
