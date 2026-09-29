# -*- coding: utf-8 -*-
"""
scrape_rubinacoffee.py

Rubina珈琲(Rubina Coffee、rubina.base.shop、栃木県佐野市赤坂町963-1。
2021年1月開業、自社製造の焙煎機「RUBINA」で注文後焙煎する自家焙煎
専門店)の商品情報を取得する。BASE(base.shopドメイン)。

【店舗発見の経緯】
全国再調査(栃木県)でサブエージェント調査から発見。

【対象商品について】
実データ確認済み(2026-09時点): 商品一覧全19件のうち、複数銘柄セット
(「旅するコーヒー3種セット」×3・「お店のオススメ珈琲3種セット」)と、
生豆(焙煎前の状態で販売する別ラインの8商品、飲用のための焙煎済み豆
とは別カテゴリのため対象外)を除いた、焙煎済みの豆7銘柄(160g、
全てストレート)を対象とする。

【商品説明の構造について】
実データ確認済み: og:descriptionが「［焙煎名／煎り度］簡潔な風味説明
生産地：X標高：Y品種：Z精製：W」に続き、「自社製造の焙煎機「RUBINA」
で最適な焙煎度合いで、ご注文を受けてから焙煎しお届けします。」という
定型文(自家焙煎の根拠でもある)が続く。この定型文以降を除去して
flavor_notes/farm_noteを抽出する。産地・品種の構造化ラベルが無い
銘柄(エルサルバドル・ケニアの一部)もある。
"""

import json
import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "Rubina珈琲（Rubina Coffee）",
    "url": "https://rubina.base.shop/",
    "platform": "BASE(base.shop)",
    "address": "栃木県佐野市赤坂町963-1",
    "prefecture": "栃木県",
    "robots_txt_status": "未確認(BASE標準構成)",
}

BASE_URL = "https://rubina.base.shop"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "85108228",  # 【ブラジル】ボンフィーノ
    "85224251",  # 【ペルー】天空のペルー
    "85224478",  # 【エチオピア】グジ ウラガ G-1
    "85224619",  # 【エルサルバドル】JAS有機(RFA認証品)
    "85224691",  # 【インドネシア】マンデリン
    "85228096",  # 【ケニア】ルイスグラシア AA++
    "85228511",  # 【コスタリカ】ロサ マウンテン
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_BRACKET_PATTERN = re.compile(r"[［\[]\s*([^］\]]+?)\s*[］\]]")
BOILERPLATE_MARKER = "自社製造の焙煎機"
LABEL_PATTERN = re.compile(r"(生産地|標高|品種|精製)[：:]\s*([^生標品精]+?)(?=(?:生産地|標高|品種|精製)[：:]|$)")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1).strip() if desc_m else ""

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else 160

    main_part = desc.split(BOILERPLATE_MARKER)[0]
    roast_m = ROAST_BRACKET_PATTERN.search(main_part)
    roast_hint = roast_m.group(1).strip() if roast_m else None
    after_bracket = ROAST_BRACKET_PATTERN.sub("", main_part, count=1)

    labels = {m.group(1): m.group(2).strip() for m in LABEL_PATTERN.finditer(after_bracket)}
    flavor_text = LABEL_PATTERN.split(after_bracket)[0].strip() or None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{item_id}"

    region = labels.get("生産地")
    if parsed["category"] != "ブレンド":
        detected = (region and detect_country_name(region)) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if region else "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精製"):
        parsed["processing_method"] = normalize_processing_method(labels["精製"])

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産地", "標高", "品種") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": flavor_text,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is None:
            continue
        records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_rubinacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rubinacoffee.json に出力しました")


if __name__ == "__main__":
    main()
