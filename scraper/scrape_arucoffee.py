# -*- coding: utf-8 -*-
"""
scrape_arucoffee.py

或る焙煎所(ARU。運営: 株式会社ARU、障害者の就労継続支援事業所、
大分県大分市長浜町1-7-6 塩九升ビル1F)の商品情報を取得する。
Shopify(aru-coffee.myshopify.com)。

【対象商品】「自家焙煎コーヒー豆」コレクションの豆(100g)。
product_typeが空のため、タイトルとバリエーション名で選別する。
除外: ドリップパック、セット(セサミスティック/ペアリングBOX)、
新太珈琲(豆300g。同銘柄の100gを代表にする)。
「Mr.ブレンド13」(高松大樹プロデュース)と「新太珈琲」(渡邉新太選手との
コラボ)は著名人とのコラボ商品だが、店のオンラインショップで自店の商品として
販売され(商品説明も「中煎りでバランス良く仕上げました」と店側の記述)、
他社焙煎と読める記載は無いため収録する。両方とも在庫なし(完売)。

【焙煎度】商品名の括弧書き(浅煎り/中煎り/深煎り/中深煎り)から取得。
Mr.ブレンド13は焙煎度の記載なし。
重量はバリエーション名の「100g」から取得。豆のまま/挽くは同価格のため
「豆のまま」(Mr.ブレンド13のみ「コーヒー豆」)を代表にする。

【更新日について】全商品の updated_at がテーマ更新で一律になっているため、
商品更新の根拠にはしない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "或る焙煎所",
    "url": "https://aru-coffee.myshopify.com/",
    "platform": "Shopify",
    "address": "大分県大分市長浜町1-7-6 塩九升ビル1F",
    "prefecture": "大分県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://aru-coffee.myshopify.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_TITLE_KEYWORDS = ["ドリップパック", "セット", "BOX"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"[(（]\s*(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)\s*[)）]")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    # 同一銘柄の重量違い(新太珈琲 100g/300g)は最小重量を代表にするため、先に集める
    candidates = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
        if any(kw in title for kw in EXCLUDE_TITLE_KEYWORDS):
            continue
        weighted = []
        for v in p["variants"]:
            m = WEIGHT_PATTERN.search(v.get("title") or "") or WEIGHT_PATTERN.search(title)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        candidates.append((title, p, weighted))

    groups = {}
    for title, p, weighted in candidates:
        key = re.sub(r"\s*\d+\s*g\s*$", "", title.replace("豆", "")).strip()
        weight = min(w for w, v in weighted)
        if key not in groups or weight < groups[key][0]:
            groups[key] = (weight, title, p, weighted)

    records = []
    for key, (weight, title, p, weighted) in groups.items():
        cands = [v for w, v in weighted if w == weight]
        variant = next((v for v in cands if "豆のまま" in (v.get("title") or "") or "コーヒー豆" in (v.get("title") or "")), cands[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body)
        desc = body[:400] or None

        name = re.sub(r"^[「」\s]*高松大樹プロデュース[」\s]*", "", title)
        name = re.sub(r"[（(]\s*100g[・･]豆or粉\s*[)）]", "", name).strip()
        name = re.sub(r"\s*豆\s*\d+g$", "", name).strip()

        parsed = parse_product(name)
        blend_components = []
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            countries = re.findall(r"(ブラジル|タンザニア|ホンジュラス|コロンビア)", body)
            if "2種類" in body or "3種類" in body:
                blend_components = [{"origin_country": c} for c in dict.fromkeys(countries)]
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if not parsed["origin_country"]:
                # 例: 新太珈琲「豆はコロンビア・ピンクブルボンを使用」
                detected = detect_country_name(body)
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "description"

        mr = ROAST_PATTERN.search(title)
        if mr:
            roast = mr.group(1)
        else:
            mb = re.search(r"(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)で", body)
            roast = mb.group(1) if mb else None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": blend_components,
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_arucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_arucoffee.json に出力しました")


if __name__ == "__main__":
    main()
