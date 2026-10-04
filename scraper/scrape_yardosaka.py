# -*- coding: utf-8 -*-
"""
scrape_yardosaka.py

YARD(大阪市天王寺区茶臼山町1-3、てんしば/天王寺公園内の自家焙煎コーヒースタンド)の商品情報を取得する。Shopify(`/products.json`)。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうちproduct_typeが「コーヒー」の商品が焙煎豆(オリジン・ブレンド)にあたる。
価格0円のメルマガ登録特典・飲み比べセットは除外。
自家焙煎の焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とし、ドリップバッグ・
セット/詰め合わせ/ギフト・定期便・生豆・器具・飲料等は除外する。
バリエーションは重量(g)を含むものを対象とし、最小重量のバリエーションの価格・重量を
代表として採用する(いずれかの在庫があれば販売中)。
焙煎度は商品名・タグ・説明文の「焙煎度/Roast level」表記から読み取れる場合のみ設定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "YARD",
    "url": "https://yard-osaka.myshopify.com/",
    "platform": "Shopify",
    "address": "大阪府大阪市天王寺区茶臼山町1-3",
    "prefecture": "大阪府",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://yard-osaka.myshopify.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.I)
LEADING_NUMBER_PATTERN = re.compile(r"^\s*(\d{2,4})(?!\d)")
EXCLUDE_KEYWORDS = (
    "ドリップバッグ", "ドリップバック", "ドリップパック", "drip bag", "dripbag", "セット", " set", "ギフト", "gift",
    "定期便", "subscription", "サブスク", "生豆", "飲み比べ", "お試し", "詰め合わせ", "詰合せ",
    "ゆうパック", "変更", "coming soon", "IN THE COFFEE KYOTO", "Tシャツ", "t-shirt", "タンブラー", "ドリッパー",
    "ミル", "グラインダー", "ケトル", "フィルター", "カフェオレ", "ベース", "チョコ", "クッキー",
)
ROAST_LABEL_PATTERN = re.compile(r"(?:焙煎度|焙煎|roast\s*level|roast)[\s】\]:：]*([^\n]{0,24})", re.I)
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り|ミディアムライト|medium\s*light", re.I)),
    ("中深煎り", re.compile(r"中深煎り|ミディアムダーク|medium\s*dark", re.I)),
    ("浅煎り", re.compile(r"浅煎り|ライト\s*ロースト|light\s*roast|\blight\b", re.I)),
    ("中煎り", re.compile(r"中煎り|ミディアム\s*ロースト|medium\s*roast|\bmedium\b", re.I)),
    ("深煎り", re.compile(r"深煎り|ダーク\s*ロースト|dark\s*roast|\bdark\b|フレンチ|イタリアン|french\s*roast", re.I)),
)
EXTRA_COUNTRIES = {}

def clean_title(title: str) -> str:
    return title



def coarse_roast(text: str) -> tuple[str | None, str | None]:
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def variant_weight(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "") or LEADING_NUMBER_PATTERN.match(title or "")
    return int(m.group(1)) if m else None


def fetch_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def is_target(p: dict, title: str) -> bool:
    lowered = title.lower()
    if any(k.lower() in lowered for k in EXCLUDE_KEYWORDS):
        return False
    return p.get("product_type") == "コーヒー"


def scrape_all_products() -> list[dict]:
    records = []
    seen_urls = set()
    for p in fetch_products():
        raw_title = re.sub(r"\s+", " ", p["title"]).strip()
        title = clean_title(raw_title)
        if not is_target(p, raw_title):
            continue

        weighted = []
        for v in p["variants"]:
            w = variant_weight(v.get("title"))
            if w:
                weighted.append((w, v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        price = int(float(variant["price"]))
        if price <= 0:
            continue
        available = any(v.get("available") for w, v in weighted if w == weight)
        if False:
            continue

        body_text = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        desc = re.sub(r"\s+", " ", body_text)[:400] or None
        tags = [t for t in (p.get("tags") or [])]
        tag_text = " ".join(tags)

        parsed = parse_product(title)
        is_blend = "ブレンド" in title or "blend" in title.lower()
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                for src, text in (("raw_name", title), ("tag", tag_text)):
                    c = detect_country_name(text)
                    if c:
                        parsed["origin_country"] = c
                        parsed["origin_source"] = src
                        break
            if not parsed["origin_country"]:
                m = re.search(r"(?:産地国?|Country|Origin)\s*[:：]\s*([^\n]+)", body_text, re.I)
                c = detect_country_name(m.group(1)) if m else None
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, tag_text)
            if not parsed["origin_country"]:
                for k, c in EXTRA_COUNTRIES.items():
                    if k in title.upper():
                        parsed["origin_country"] = c
                        parsed["origin_source"] = "raw_name"
                        break

        roast_level, roast_hint = coarse_roast(title)
        if not roast_level:
            roast_level, roast_hint = coarse_roast(tag_text)
        if not roast_level:
            m = ROAST_LABEL_PATTERN.search(body_text)
            if m:
                roast_level, roast_hint = coarse_roast(m.group(1))
        if not roast_level and "ロースト" in title:
            roast_level = parsed["roast_level"]

        url = f"{BASE_URL}/products/{p['handle']}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        status = "販売中" if available else "完売"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": status,
            "out_of_stock": status != "販売中",
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yardosaka.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yardosaka.json に出力しました")


if __name__ == "__main__":
    main()
