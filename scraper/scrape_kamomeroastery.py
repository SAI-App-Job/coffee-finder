# -*- coding: utf-8 -*-
"""
scrape_kamomeroastery.py

カモメロースタリ東京(kamome-tokyo.com、東京都葛飾区亀有3-36-2 1F、2023年開業の
カフェ併設のスペシャルティコーヒー自家焙煎店。ゲイシャが主力)の商品情報を取得する。
Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`から全商品ページURLを列挙し、
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を取得する。
同じ銘柄が「コーヒー豆100g」と「コーヒー豆300g(『モンスーン』のみ250g)」の
別商品として並ぶため、他店舗と同様に最小サイズ(100g)の商品のみを代表として収録する
(300g/250g版は同一銘柄の大容量版のため除外)。全商品が「受注後焙煎」。
ゲイシャ飲み比べ ギフトポーチセット等のセット商品は対象外。
商品名の「コーヒー豆100g 【受注後焙煎】」はサイズ・販売形態を示す定型句のため
raw_nameから除去する。
"""

import html
import json
import re
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method, normalize_processing_method

SHOP_INFO = {
    "name": "カモメロースタリ東京",
    "url": "https://www.kamome-tokyo.com/",
    "platform": "Wix(Wix Stores)",
    "address": "東京都葛飾区亀有3-36-2 1F",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.kamome-tokyo.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
SIZE_PATTERN = re.compile(r"\s*コーヒー豆\s*(\d+)\s*g\s*(?:【受注後焙煎】)?\s*$")
EXCLUDE_KEYWORDS = ("ギフト", "セット", "コーヒーバッグ", "ドリップバッグ")

# 銘柄名・説明から産地が判別できないもの(説明文の産地記載による)
ORIGIN_OVERRIDES: dict[str, str] = {}  # 説明文に産地記載が無い銘柄(モンスーン)は産地不明のまま


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def clean_name(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("『", " ").replace("』", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_record(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))
    full_name = clean_name(ld.get("name", ""))
    size_m = SIZE_PATTERN.search(full_name)
    if not size_m or int(size_m.group(1)) != 100:  # 100g版のみ(300g/250g版・セット類は除外)
        return None
    if any(kw in full_name for kw in EXCLUDE_KEYWORDS):
        return None
    name = SIZE_PATTERN.sub("", full_name).strip()

    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()
    desc = re.sub(r"^●", "", desc)
    # 説明文の後半は「豆のまま/挽き度合」の注文方法や送料の定型文のため、その手前で打ち切る
    desc = re.split(r"●(?:焙煎度について|『豆のまま』|２袋のご注文)", desc)[0].strip()[:500] or None
    full_desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or ""))
    roast_rec = re.search(r"焙煎度は[^【]{0,40}【([^】]*煎り)】", full_desc)
    proc_m = re.search(r"精製方法[：:]\s*([^\s●。]+)", full_desc)
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            override = next((v for k, v in ORIGIN_OVERRIDES.items() if k in name), None)
            if override:
                parsed["origin_country"] = override
                parsed["origin_source"] = "description"
        if not parsed["origin_country"]:
            detected = detect_country_name(name) or detect_country_name(desc or "")
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or (normalize_processing_method(proc_m.group(1)) if proc_m else None) or detect_processing_method(name),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": "受注後焙煎" + (f"(おすすめ: {roast_rec.group(1)})" if roast_rec else ""),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            record = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kamomeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kamomeroastery.json に出力しました")


if __name__ == "__main__":
    main()
