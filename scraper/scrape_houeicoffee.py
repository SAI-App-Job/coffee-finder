# -*- coding: utf-8 -*-
"""
scrape_houeicoffee.py

HOUEI COFFEE and STORE(ホウエイコーヒー、https://houeicoffee.thebase.in、千葉県成田市東町601-2)の商品情報を取得する。BASE。
成田山門前店(テイクアウト専門・焙煎所)と、カフェ公津の杜店(成田市公津の杜1-27-3)の2店舗。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。

【販売先の採用について】
楽天市場にも出店しているが、公式サイト(houeicoffee.com)の「ONLINE SHOP」リンク先であるBASEを採用。
BASEには全豆銘柄(11銘柄)が200gの単品で揃い、価格・在庫・説明を商品ページで確認できるため。

【対象商品について】
実データ確認済み(2026-10-26時点): トップ(2ページ・計28商品)のうち、焙煎豆11銘柄
(ブレンド5・シングル5・デカフェ1)を対象とする。各銘柄は200g単品(豆のまま/細・中・粗挽きの選択式)。
お試しセット(2)・ギフト(200g×2/×3、ドリップパック、リキッド)・エコバッグ付きセット・
アイスコーヒーリキッド・ドリップパック・ドリッパー(器具)は除外。
商品名は商品ページのタイトルから「200g」等の付帯表記と英語併記を除いたもの。
価格・在庫・説明は商品ページから取得する。焙煎度は商品説明にある銘柄(ブレンドの
「ハイロースト」「イタリアンロースト」)のみ記載し、その他は店が明示していないためnull。

【在庫について】
購入ページのバリエーション(豆/粉)のうち豆の在庫が「在庫なし」なら完売とする。

【住所について】
特定商取引法に基づく表記(/law)の事業者所在地(〒286-0025 千葉県成田市東町601-2)を採用。
公式サイトの成田山門前店(焙煎所)の所在地と同じ。

【robots.txtについて】
User-agent: * は /cart/ /web_cart/ /shops/ 等のみDisallow(商品ページは許可)。python-requests/curl
は個別にDisallowのため、識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "HOUEI COFFEE and STORE",
    "url": "https://houeicoffee.thebase.in/",
    "platform": "BASE",
    "address": "千葉県成田市東町601-2",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(User-agent: * は /cart/ 等のみDisallow。python-requests/curl等は個別にDisallowのため識別UAを使用、間隔5秒以上)",
    "source_note": "BASE https://houeicoffee.thebase.in/ (トップ2ページ・/law)と各商品ページ、公式 https://houeicoffee.com/ (自家焙煎・店舗の記載)を2026-10-26に確認。BASEは更新日の表示なし",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://houeicoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5

# id: 商品ID / name: 表示名 / category: Noneなら自動判定 / blend: ブレンドの構成国(商品説明)
# roast / roast_hint: 商品説明に焙煎度の記載がある銘柄のみ
ITEMS = [
    {"id": "28835", "name": "HOUEI COFFEE ブレンド", "blend": ["ブラジル", "コロンビア", "グアテマラ"], "roast_hint": "ハイロースト"},
    {"id": "1008373", "name": "HOUEI COFFEE プレミアム ブレンド", "blend": ["ブラジル", "コロンビア", "グアテマラ", "エチオピア"]},
    {"id": "487564", "name": "モカブレンド", "blend": ["エチオピア", "ブラジル", "コロンビア"]},
    {"id": "909918", "name": "NARITA ブレンド", "blend": ["インドネシア", "コロンビア", "グアテマラ", "エチオピア"]},
    {"id": "175641", "name": "エスプレッソ ブレンド", "blend": ["ブラジル", "コロンビア", "グアテマラ"], "roast": "深煎り", "roast_hint": "イタリアンロースト"},
    {"id": "909830", "name": "インドネシア マンデリン ビンタンリマ"},
    {"id": "487488", "name": "ブラジル サントアントニオ農園 プレミアムショコラ"},
    {"id": "175647", "name": "エチオピア シダモG2"},
    {"id": "487535", "name": "グアテマラ アゾテア農園 SHB"},
    {"id": "487522", "name": "コロンビア マグダレナ SUP"},
    {"id": "1474136", "name": "コロンビア カフェインレス", "category": "デカフェ", "origin": "コロンビア"},
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_PATTERN = re.compile(
    r'<p class="cot-itemOrder-variationName"[^>]*>([^<]*)</p>\s*'
    r'(?:<p class="cot-itemOrder-variationStock"[^>]*>([^<]*)</p>)?'
)
GROUND_KEYWORDS = ("粉", "挽", "ドリップ")
ROAST_PATTERN = re.compile(r"焙煎\s*[：:]\s*(極深煎|中深煎|深煎|中浅煎|浅煎|中煎)")
PROCESS_PATTERN = re.compile(r"(?:精製方法|処理方法)\s*[：:]\s*([^\s、。\n]+)")


def is_sold_out(html_text: str) -> bool:
    """豆(挽いていない)のバリエーションが全て在庫なしなら完売。バリエーションが無ければ購入可否で判定する。"""
    bean_variations = [
        (name, stock.strip())
        for name, stock in VARIATION_PATTERN.findall(html_text)
        if not any(k in name for k in GROUND_KEYWORDS)
    ]
    if bean_variations:
        return all(stock == "在庫なし" for _, stock in bean_variations)
    m = PURCHASABILITY_PATTERN.search(html_text)
    return bool(m) and m.group(1) == "unpurchasable"


def build_record(item: dict) -> dict | None:
    item_url = f"{BASE_URL}/items/{item['id']}"
    resp = requests.get(item_url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = (desc_m.group(1) if desc_m else "").replace("&#39;", "'").replace("&amp;", "&")
    desc = re.sub(r"\s+", " ", raw_desc).replace("新鮮な膨らむコーヒー豆をご自宅で。", "").replace("【送料無料】", "").strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    sold_out = is_sold_out(html_text)

    roast_m = ROAST_PATTERN.search(raw_desc)
    roast = (roast_m.group(1) + "り") if roast_m else None
    proc_m = PROCESS_PATTERN.search(raw_desc)
    process = normalize_processing_method(proc_m.group(1)) if proc_m else None

    name = item["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item.get("category"):
        parsed["category"] = item["category"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item.get("origin"):
            parsed["origin_country"] = item["origin"]
            parsed["origin_source"] = "raw_name"
    if process:
        parsed["processing_method"] = process

    blend_components = [{"origin_country": c, "percentage": None} for c in item.get("blend", [])]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": item.get("roast") or roast or parsed["roast_level"],
        "roast_hint": item.get("roast_hint"),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": 200,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for idx, item in enumerate(ITEMS):
        if idx:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_houeicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_houeicoffee.json に出力しました")


if __name__ == "__main__":
    main()
