# -*- coding: utf-8 -*-
"""
scrape_ashijima.py

葦島珈琲(喫茶葦島、ashijimacoffee.online、京都府京都市中京区大黒町37
文明堂ビル5階、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(www.kitsune-coffee.com「京都のおすすめコーヒー豆
専門店15選」)で発見。本店(三条通河原町)の他、京都髙島屋4階にも出店(2拠点)。

【対象商品について】
実データ確認済み(/products.json全54件、2026-09時点): product_typeが
未設定のため商品名で判別する必要がある。抽出器具・ロゴ入り手提げ袋・
チーズケーキ・熨斗紙・一杯用ドリップ珈琲(6件)・ブレンドセット/三種の
ブレンドセット(重量違い、複数銘柄の詰め合わせ)・定期便に加え、「藍 ai」
「晨 aki」「深炭 misumi」(3種)は説明文を確認したところ丹波焼作家との
コラボによる菓子皿等の陶器であることが判明し対象外(コーヒー豆ではない)。
最終的にコーヒー豆10件(ストレート7・ブレンド3、いずれも100g)を対象とする
ハンドル名の明示的な許可リストを採用した(命名パターンが多様でキーワード
除外だけでは陶器類等の誤検出を防ぎきれないため)。

【商品説明の構造について】
実データ確認済み: body_htmlが「手提げ袋は別売りの案内(定型文、除去)→
テイスティング文→焙煎度：X(ラベル)→表示代金は税込です以降の配送・
賞味期限に関する定型文(除去)」という構成。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "葦島珈琲",
    "url": "https://ashijimacoffee.com/",
    "platform": "Shopify",
    "address": "京都府京都市中京区三条通河原町東入大黒町37 文明堂京都ビル5階",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://ashijimacoffee.online"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_HANDLES = {
    "カフェインレス-コロンビア産-深煎り",
    "インドネシア-マンデリン-sg-深煎り",
    "ジャマイカ-ブルーマウンテン-no-1-クライスデール-中深煎り",
    "イエメンモカマタリ-100g",
    "トラジャ-ランテカルラ農園-深煎り",
    "エチオピア-モカ-g1-中煎り",
    "ブラジル-サンタカタリーナ農園-キャラメラード-中深煎り",
    "深煎りブレンド-深煎り",
    "綾小路ブレンド-中深煎り",
    "三条ブレンド",
}


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return [p for p in resp.json().get("products", []) if p["handle"] in TARGET_HANDLES]


def parse_flavor_and_roast(body_html: str) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    for a in soup.find_all("a"):
        a.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [l for l in text.split("\n") if l.strip()]

    flavor_lines = []
    roast = None
    for line in lines:
        if "手提げ袋" in line:
            continue
        if line.startswith("＊表示代金"):
            break
        m = re.match(r"^焙煎度\s*[：:]\s*(.+)$", line)
        if m:
            roast = m.group(1).strip()
            continue
        flavor_lines.append(line)

    return ("\n".join(flavor_lines) if flavor_lines else None), roast


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    variant = next((v for v in product["variants"] if "100g" in (v.get("title") or "")), product["variants"][0])
    price = int(float(variant["price"]))

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": f"{BASE_URL}/products/{product['handle']}",
        }

    parsed = apply_category_hint_fallback(parsed, title)
    flavor_notes, roast_note = parse_flavor_and_roast(product.get("body_html"))
    if roast_note:
        roast_parsed = parse_product(roast_note)
        if roast_parsed.get("roast_level"):
            parsed["roast_level"] = roast_parsed["roast_level"]

    stock_status = detect_stock_status(title)

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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_ashijima.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ashijima.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
