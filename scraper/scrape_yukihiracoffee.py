# -*- coding: utf-8 -*-
"""
scrape_yukihiracoffee.py

YUKIHIRA COFFEE(https://www.yukihiracoffee.com/、〒990-0401 山形県東村山郡中山町長崎412、
特定商取引法に基づく表記・aboutで確認)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(山形県)の新規発掘。

【自店焙煎の根拠】
公式の全コーヒー豆商品ページに「毎週月・火曜日に焙煎するため、ご注文から7日以内に発送致します」
(定休日は月・火曜日)とあり、aboutに「コーヒーを飲むシーンに合わせて生豆をセレクトしております」、
自宅焙煎セット(生豆・雪平鍋焙煎)の案内もある。「自家焙煎」の語そのものは公式サイトに無いが、
生豆の選定と焙煎を店が自ら行い発送している記述と判断して収録する。

【対象商品について】
実データ確認済み(2026-10-13時点): sitemap.xmlの商品は全33件。コーヒー豆は、
朝/お昼/夜/まったり/リフレッシュの5銘柄(各100g・150g。重量違いは最小の100gを代表に採用)、
有機ノンカフェイン(100g)、COEロット、コンドールファーメンテーション、発酵コーヒー(Solsticio)の9銘柄。
除外: 150g版、インフューズドコーヒー(ゲイシャピーチ)、ギフト・ドリップパック・飲み比べセット・
福袋、卸販売、COLD BREW・ONE LIQUID・CRAFT COFFEE(ボトル液体)、自宅焙煎セット(生豆)、
スケール・ステッカー。
og:descriptionは空のため、商品説明本文から「▼カップテイスト」欄(味の説明)と精製方法を取得する。
焙煎度は商品ページの「焙煎度：」表記(シナモン/ミディアム/フルシティ/シティ)。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import html as _html
import json
import re

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "YUKIHIRA COFFEE",
    "url": "https://www.yukihiracoffee.com/",
    "platform": "BASE",
    "address": "山形県東村山郡中山町長崎412",
    "prefecture": "山形県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.yukihiracoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き, 産地, 焙煎度)
ITEMS = [
    ("134540582", "COEロット エルサルバドル 2025 COE1 LAS DUANAS", 100, None, "エルサルバドル", "シナモンロースト"),
    ("156225198", "コンドールファーメンテーションコーヒー コロンビア ラス・フローレス", 100, None, "コロンビア", "シナモンロースト"),
    ("58579787", "発酵コーヒー コロンビア ロス パティオス ソルシティシオ", 100, None, "コロンビア", "シナモンロースト"),
    ("98375901", "朝のコーヒー ブラジル シティオダトーレ", 100, None, "ブラジル", "ミディアムロースト"),
    ("125574189", "お昼のコーヒー豆 タンザニア テンボテンボ", 100, None, "タンザニア", "フルシティロースト"),
    ("125574127", "夜のコーヒー豆 エチオピア ゲルシ", 100, None, "エチオピア", "ミディアムロースト"),
    ("125574294", "まったりするコーヒー豆 インドネシア PUTORA GAYO", 100, None, "インドネシア", "フルシティロースト"),
    ("58238888", "リフレッシュコーヒー ケニア キマツ・ファクトリー", 100, None, "ケニア", "ミディアムロースト"),
    ("58238990", "有機ノンカフェインコーヒー メキシコ チアパス", 100, "デカフェ", "メキシコ", "シティロースト"),
]

# 商品ページの「精製方法：」表記が正規化辞書で解釈できないものは、ページの表記どおりに明示する
PROCESSING_OVERRIDES = {
    "134540582": "ウォッシュド・アナエロビック",  # Washed Anaerobic
    "156225198": "コンドール・ファーメンテーション(ウォッシュド)",  # Condor Fermentation Washed
    "58579787": "コ・ファーメンテーション",  # Co-fermantation
}

PRICE_PATTERN =re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
BODY_START = "通報する"
BODY_END = "ショップの評価"


def body_text(html_text: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_text, flags=re.S)
    t = _html.unescape(re.sub(r"<[^>]+>", "\n", t))
    t = re.sub(r"[ \t　]*\n\s*", "\n", t)
    a = t.find(BODY_START)
    b = t.find(BODY_END, a if a >= 0 else 0)
    if a < 0 or b < 0:
        return ""
    return t[a + len(BODY_START):b].strip()


def extract_taste(body: str) -> str | None:
    m = re.search(r"▼カップテイスト\n(.*?)(?=\n▼|\Z)", body, re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()[:400] or None


def build_record(item_id, name, weight_g, category_override, origin, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text
    body = body_text(html_text)

    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    detected = detect_country_name(name)
    if detected and not parsed["origin_country"]:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, name)
    if origin:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin in name else "description"
    if category_override:
        parsed["category"] = category_override

    method = parsed["processing_method"]
    if not method:
        method = extract_from_description(body)["processing_method"]

    method = PROCESSING_OVERRIDES.get(item_id, method)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": method,
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": extract_taste(body),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(*item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yukihiracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yukihiracoffee.json に出力しました")


if __name__ == "__main__":
    main()
