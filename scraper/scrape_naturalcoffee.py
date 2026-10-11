# -*- coding: utf-8 -*-
"""
scrape_naturalcoffee.py

Natural Coffee(natural.coffee、熊本県熊本市北区下硯川町1792-12。株式会社ナチュラルコーヒー)
の商品情報を取得する。Shopify。

【店舗発見の経緯】
全国再調査(熊本県)で発見。商品の説明タグに「直火」「自家焙煎」が明記されている。

【住所について】
公式サイトの「アクセス」および特定商取引法の表記はいずれも「〒861-5522 熊本県熊本市北区
下硯川町1792-12」(ショップ&カフェ兼所在地)。豆ナビ等に出る「1045-9」は公式サイトでは
確認できなかったため採用しない。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`(59件)のうち、product_typeが
「レギュラーコーヒー」「アイスコーヒー」「コーヒー」の商品で「豆」バリエーションを持つもの。
除外: 業務用(500g)、ドリップバッグ、ギフト・セット・お得用多袋セット、紅茶・カレー・器具、
シナモン入りコーヒー(風味付け)、「N-POST便商品」(同銘柄の通常商品の送り方違いの重複)。
ただしN-POST便にしか存在しない「特選ブレンド 浅煎り」のみ収録する。
「豆 / 200g」のようにバリエーションが「豆」「粉」に分かれているため、「豆」の最小重量
(多くは200g、一部150g)の価格・在庫を代表とする。重量表記が無い商品(イプレリコーヒー)は
商品名の「内容量200g」から取る。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Natural Coffee",
    "url": "https://natural.coffee/",
    "platform": "Shopify",
    "address": "熊本県熊本市北区下硯川町1792-12",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://natural.coffee"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = {"レギュラーコーヒー", "アイスコーヒー", "コーヒー"}
EXCLUDE_WORDS = ("業務用", "セット", "ギフト", "ドリップ", "シナモン", "お徳用")
# N-POST便にしか存在しない銘柄(handle)。それ以外のN-POST便は通常商品の重複なので除外
NPOST_ALLOW = {"n-post便商品-特選ブレンドコーヒー-浅煎り-ミディアムロースト"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
ROAST_WORDS = ["中深煎り", "中浅煎り", "深煎り", "中煎り", "浅煎り"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


def scrape_all_products() -> list[dict]:
    products = []
    for page in range(1, 5):
        r = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        batch = r.json().get("products", [])
        if not batch:
            break
        products += batch

    records = []
    for p in products:
        if p.get("product_type") not in BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(w in title for w in EXCLUDE_WORDS):
            continue
        if "N-POST" in title and p["handle"] not in NPOST_ALLOW:
            continue
        title = re.sub(r"【N-POST便商品】\s*", "", title)
        title = re.sub(r"^NEW!!\s*季節限定商品！\s*", "", title)

        weighted = []
        for v in p["variants"]:
            vt = norm(v.get("title") or "")
            if not vt.startswith("豆"):
                continue
            m = WEIGHT_PATTERN.search(vt) or WEIGHT_PATTERN.search(norm(title))
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = norm(BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        desc = body[:400] or None
        tags = p.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        parsed = parse_product(title)
        is_blend = "ブレンド" in title or "ブレンド" in tags
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                detected = detect_country_name(title) or ("スリランカ" if "スリランカ" in title else None)
                if not detected:
                    m = re.search(r"(?:生豆生産国|原産国)\s*[:：]\s*(\S+)", body)
                    detected = detect_country_name(m.group(1)) if m else None
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)

        # 商品名の「イプレリコーヒーライト」の「ライト」を焙煎度と誤認しないよう、焙煎度は別途判定する
        roast_level = parse_product(title.replace("イプレリコーヒーライト", "イプレリコーヒー"))["roast_level"]
        if not roast_level:
            m = re.search(r"焙煎度合い[・:：]\s*(\S*?ロースト)", body)
            if m:
                roast_level = parse_product(m.group(1))["roast_level"]
        roast_hint = next((w for w in ROAST_WORDS if w in title), None)
        if not roast_level and roast_hint:
            roast_level = roast_hint

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
            "roast_hint": roast_hint if roast_level != roast_hint else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
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
    with open("data_naturalcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_naturalcoffee.json に出力しました")


if __name__ == "__main__":
    main()
