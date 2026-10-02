# -*- coding: utf-8 -*-
"""
scrape_mamenoyakata.py

自家焙煎珈琲豆の館(珈琲豆の館、千葉県山武市成東668-6 富楽モール1A号室、coffeemamenoyakata.com)の
商品情報を取得する。電話・来店で注文する自家焙煎店(店舗は1店)。WordPress上の1ページ
(/list/ 取り扱い珈琲豆一覧)に、焙煎度の見出し(h2: 浅煎り/中・浅煎り/中煎り/中深煎り/
中・中深煎り/深煎り/ブレンド)と銘柄名(h3)・原産国・説明・100g価格が並ぶ。

【対象商品について】
実データ確認済み(2026-10時点、お知らせの最終更新2026-09-21): HTMLコメントアウトされている
銘柄(取り扱い終了・休止中のもの)は除外し、公開されている21銘柄(ストレート17・ブレンド4、
うちデカフェ1)を対象とする。全て100gの税込価格を代表重量・価格とする。
在庫表示は無く、掲載中=販売中として扱う。焙煎度は見出しの区分から付与し、「中・浅煎り」は
中浅煎り、「中・中深煎り」は中煎り〜中深煎りとする(原文は roast_hint に保持)。
オーガニック・自然栽培・レインフォレスト・アライアンス認証などの表記は farm_note に保持する。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆の館",
    "url": "https://coffeemamenoyakata.com/",
    "platform": "WordPress(電話・来店注文)",
    "address": "千葉県山武市成東668-6 富楽モール1A号室",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

LIST_URL = "https://coffeemamenoyakata.com/list/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ROAST_MAP = {
    "浅煎り": "浅煎り",
    "中・浅煎り": "中浅煎り",
    "中煎り": "中煎り",
    "中深煎り": "中深煎り",
    "中・中深煎り": "中煎り〜中深煎り",
    "深煎り": "深煎り",
}
CERT_KEYWORDS = ("自然栽培オーガニック", "自然栽培", "オーガニック", "レインフォレスト・アライアンス認証", "天然酵母で発酵")


def scrape_all_products() -> list[dict]:
    resp = requests.get(LIST_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup

    records = []
    section = None
    for h in main.find_all(["h2", "h3"]):
        if h.name == "h2":
            section = h.get_text(strip=True)
            continue
        if section is None or h.find_parent("aside") or h.find_parent("footer"):
            continue
        name = h.get_text(strip=True)
        # 次の見出しまでの兄弟要素を集める
        parts = []
        for sib in h.next_siblings:
            if getattr(sib, "name", None) in ("h2", "h3"):
                break
            parts.append(sib)
        block = BeautifulSoup("".join(str(p) for p in parts), "html.parser")
        text = block.get_text("\n", strip=True)
        pm = re.search(r"(\d+)\s*g\s*[￥¥]\s*([\d,]+)", text)
        if not pm:
            continue
        om = re.search(r"原産国[：:]\s*(\S+)", text)
        origin_text = om.group(1) if om else None
        p_el = block.select_one("div.column-right p")
        desc = p_el.get_text(" ", strip=True) if p_el else None
        certs = []
        for kw in CERT_KEYWORDS:
            if kw in text and not any(kw in c for c in certs):
                certs.append(kw)

        is_blend = section == "ブレンド" or "ブレンド" in name
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"] and origin_text:
                c = detect_country_name(origin_text)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "category_hint"
            parsed = apply_category_hint_fallback(parsed, origin_text or "")

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": ROAST_MAP.get(section),
            "roast_hint": None if section == "ブレンド" else section,
            "flavor_notes": desc,
            "farm_note": "、".join(certs) if certs else None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(pm.group(2).replace(",", "")),
            "weight_g": int(pm.group(1)),
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{LIST_URL}#{quote(name)}",  # 全商品が同一ページのため、商品IDを一意にするフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamenoyakata.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamenoyakata.json に出力しました")


if __name__ == "__main__":
    main()
