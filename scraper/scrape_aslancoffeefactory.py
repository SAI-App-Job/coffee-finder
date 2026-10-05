# -*- coding: utf-8 -*-
"""
scrape_aslancoffeefactory.py

ASLAN Coffee Factory(https://aslancoffeefactory.store/、福岡県北九州市小倉南区上葛原1-9-41
キヘイビル102)の商品情報を取得する。Shopify(`/products.json`)。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`33件のうち、焙煎豆(シングルオリジン・
ブレンド・デカフェ)のみを対象とする。定期便・ギークボックス(詰め合わせ)・水出しパック・
ドリップバッグ詰め合わせ・器具類は除外。
バリエーションは「14g/42g/112g(14g×8)/448g」型と「100g/200g/400g/1kg」型があるため、
100g以上(14g・42gの少量パックは使わない)の最小重量バリエーションの価格を代表とする
(112gまたは100g。粉・水出しパックの選択肢は除外し、豆のまま売りの価格を採用)。
変種なし(Default Title)の1商品のみ、商品名の「(100g~)」表記から重量を取る。
「Coming soon」表記の商品は購入不可(available=false)のため「完売」扱いとする。
焙煎度・精製方法は商品説明の「ローストレベル/焙煎度」「精製方法」欄から取得する。
自家焙煎の根拠: 商品説明が「ASLAN Coffee Factoryの焙煎士として」の記述、焙煎プロファイル
(1crak+◯sec・DTR%)つきのロースターズコメントである(焙煎機名の記述は未確認)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
    ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "ASLAN Coffee Factory",
    "url": "https://aslancoffeefactory.store/",
    "platform": "Shopify",
    "address": "福岡県北九州市小倉南区上葛原1-9-41 キヘイビル102",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://aslancoffeefactory.store"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.I)
TITLE_WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*g\s*[~〜～]")
MIN_WEIGHT_G = 100  # 14g・42gの少量パックは代表にしない
EXCLUDE_TITLE_KEYWORDS = (
    "定期便", "ギークボックス", "水出し", "ドリップバッグ", "詰め合わせ", "詰合せ", "セット",
    "ドリッパー", "フィルター", "ボトル", "bottle", "V60", "meteor",
)
EXCLUDE_VARIANT_KEYWORDS = ("粉", "水出し")

COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り|ミディアムライト|medium\s*light", re.I)),
    ("中深煎り", re.compile(r"中深煎り|ミディアムダーク|medium\s*dark", re.I)),
    ("浅煎り", re.compile(r"浅煎り|ライト\s*ロースト|light\s*roast|\blight\b", re.I)),
    ("中煎り", re.compile(r"中煎り|ミディアム\s*ロースト|medium\s*roast|\bmedium\b", re.I)),
    ("深煎り", re.compile(r"深煎り|ダーク\s*ロースト|dark\s*roast|\bdark\b|フレンチ|イタリアン|french\s*roast", re.I)),
)
ROAST_LABEL_PATTERN = re.compile(r"(?:ローストレベル|焙煎度|roast\s*level)[\s】\]:：]*([^\n]{0,60})", re.I)
FLAVOR_ANCHORS = ("フレーバーテキスト", "FLAVOR COMMENT", "CUP COMMENT", "【Aroma")
BLEND_MARKERS = ("ブレンド内容", "Blend Info", "ブレンド")


def coarse_roast(text: str) -> tuple[str | None, str | None]:
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def variant_weight(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    if not m:
        return None
    value = float(m.group(1))
    return int(round(value * 1000)) if m.group(2).lower() == "kg" else int(round(value))


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.replace("　", " ")).strip()
    t = re.sub(r"^【\s*Coming soon[！!]*\s*】\s*", "", t, flags=re.I)
    t = re.sub(r"\s*[（(]\s*\d+\s*g\s*[~〜～]\s*[）)]\s*$", "", t)
    t = re.sub(r"\s*[（(]\s*\d+\s*g\s*[~〜～]\s*[）)]", "", t)
    return t.strip()


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_representative(p: dict, title: str):
    """(重量, 価格, 販売中か) を返す。取れなければNone。"""
    weighted = []
    for v in p["variants"]:
        vt = v.get("title") or ""
        if any(k in vt for k in EXCLUDE_VARIANT_KEYWORDS):
            continue
        w = variant_weight(vt)
        if w and w >= MIN_WEIGHT_G:
            weighted.append((w, v))
    if weighted:
        weight = min(w for w, _ in weighted)
        same = [v for w, v in weighted if w == weight]
        price = int(float(same[0]["price"]))
        available = any(v.get("available") for v in same)
        return weight, price, available
    # 変種が「Default Title」のみの商品は、商品名の「(100g~)」表記から重量を取る
    m = TITLE_WEIGHT_PATTERN.search(title)
    if m and int(m.group(1)) >= MIN_WEIGHT_G and len(p["variants"]) == 1:
        v = p["variants"][0]
        return int(m.group(1)), int(float(v["price"])), bool(v.get("available"))
    return None


def build_flavor_notes(body_text: str) -> str | None:
    start = 0
    for anchor in FLAVOR_ANCHORS:
        i = body_text.find(anchor)
        if i != -1:
            start = i
            break
    text = body_text[start:]
    text = re.sub(r"フレーバーテキスト\s*★は強さ[^\n]*", "", text)
    text = re.sub(r"[（(]編集中[^）)]*[）)]", "", text)
    text = re.sub(r"★+", "", text)
    return re.sub(r"\s+", " ", text).strip()[:400] or None


def fine_roast(text: str) -> str | None:
    """「シティ～フルシティロースト」等、粗い区分に当てはまらない表記は焙煎度名で補う。"""
    for kw, roast in ROAST_KEYWORDS.items():
        if kw in (text or ""):
            return roast
    return None


def scrape_all_products() -> list[dict]:
    records = []
    seen_urls = set()
    for p in fetch_products():
        raw_title = re.sub(r"\s+", " ", p["title"].replace("　", " ")).strip()
        if any(k.lower() in raw_title.lower() for k in EXCLUDE_TITLE_KEYWORDS):
            continue
        rep = pick_representative(p, raw_title)
        if not rep:
            continue
        weight, price, available = rep
        if price <= 0:
            continue
        title = clean_title(raw_title)

        body_text = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
        # ブレンドは説明文のブレンド内容欄、または商品名の「ブレンド」で判定する
        is_blend = ("ブレンド" in title) or any(k in body_text for k in ("ブレンド内容", "Blend Info"))

        parsed = parse_product(title)
        desc_info = extract_from_description(body_text)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            parsed["grade"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                detected = detect_country_name(title)
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "raw_name"
            if not parsed["origin_country"]:
                m = re.search(r"生産国[\s:：]*([^\n]+)", body_text)
                c = detect_country_name(m.group(1)) if m else None
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)
        processing = parsed["processing_method"] or desc_info["processing_method"]
        if is_blend:
            processing = None

        roast_level, roast_hint = coarse_roast(title)
        if not roast_level:
            m = ROAST_LABEL_PATTERN.search(body_text)
            if m:
                roast_level, roast_hint = coarse_roast(m.group(1))
                if not roast_level:
                    # 「シティ～フルシティロースト」等の範囲表記は、冒頭の紹介文の「中深煎り」等を優先する
                    roast_level, _ = coarse_roast(body_text[:150])
                if not roast_level:
                    roast_level = fine_roast(m.group(1))
                if roast_level:
                    roast_hint = re.sub(r"\s+", " ", m.group(1)).strip()

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
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_hint,
            "flavor_notes": build_flavor_notes(body_text),
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
    with open("data_aslancoffeefactory.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_aslancoffeefactory.json に出力しました")


if __name__ == "__main__":
    main()
