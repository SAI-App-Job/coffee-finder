# -*- coding: utf-8 -*-
"""
scrape_pulaucoffeeroaster.py

プラウコーヒーロースター(shop.pulaucoffeeroaster.com、福島県須賀川市和田道5-11)の
商品情報を取得する。独自ドメインのBASE。

【店舗発見の経緯】
全国再調査(福島県)の新規発掘で発見。

【住所について】
/law(特定商取引法)の事業者所在地に「〒962-0818 福島県須賀川市和田道5-11」と記載(Shift_JIS)。

【対象商品について】
実データ確認済み(2026-10-12、sitemap.xmlの商品全24件): コーヒー豆14銘柄(ストレート13・
カフェインレス1、いずれも200g)と、非対象のドリップバッグ・コーヒーバッグ各種・セレクトセット・
珈琲ゼリー・珈琲甘酒・ハニーナッツ・ギフトセット。NON_BEAN_KEYWORDSで除外する。
ブレンドは現行ラインナップに無し。
焙煎度は購入者が注文時に選ぶ方式(浅煎り〜深煎り)で商品固有の焙煎度が無いため、商品名から
判定できるもの以外はNullとする。重量は全商品「焙煎後200g」(商品名/説明に明記)。
価格はOGPのproduct:price:amount(税込、200g)。在庫はitem_purchasabilityで判定。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "プラウコーヒーロースター",
    "url": "https://shop.pulaucoffeeroaster.com/",
    "platform": "BASE(独自ドメイン)",
    "address": "福島県須賀川市和田道5-11",
    "prefecture": "福島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.pulaucoffeeroaster.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["セット", "ドリップバッグ", "コーヒーバッグ", "ゼリー", "甘酒", "ナッツ", "水出し", "ギフト"]
DEFAULT_WEIGHT_G = 200

# 国名が商品名に無い(銘柄名のみの)商品の産地
ORIGIN_OVERRIDES = {
    "40827012": "インドネシア",  # トラジャ ランテカルア スロトコ農園(スラウェシ島)
    "48825866": "エチオピア",    # モカ シャキッソ タデジジ農園 カフェインレス
}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(?:g|グラム)")


def unescape(s: str) -> str:
    import html
    return html.unescape(s)


def fetch_item_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    ids = re.findall(r"/items/(\d+)", resp.text)
    return list(dict.fromkeys(ids))


def clean_name(title: str) -> str:
    name = unescape(title).split(" | ")[0]
    name = re.sub(r"コーヒー?[ー－]?豆", "", name)
    name = re.sub(r"コーヒ[－ー]豆", "", name)
    name = re.sub(r"\s*\d+\s*(?:g|グラム)\s*$", "", name)
    name = name.replace("◆", "")
    return re.sub(r"\s+", " ", name).strip()


def build_record(item_id: str) -> dict | None:
    url = f"{BASE_URL}/items/{item_id}"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    raw_title = unescape(title_m.group(1)).split(" | ")[0]
    if any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None
    name = clean_name(raw_title)

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    weight_m = WEIGHT_PATTERN.search(raw_title)
    weight_g = int(weight_m.group(1)) if weight_m else DEFAULT_WEIGHT_G

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "description"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in fetch_item_ids():
        try:
            record = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_pulaucoffeeroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pulaucoffeeroaster.json に出力しました")


if __name__ == "__main__":
    main()
