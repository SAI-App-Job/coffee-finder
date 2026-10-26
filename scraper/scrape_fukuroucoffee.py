# -*- coding: utf-8 -*-
"""
scrape_fukuroucoffee.py

ふくろう珈琲(ふくろう珈琲合同会社、https://netshop.fukuroucoffee.co.jp、千葉県船橋市行田1-45-17 塚田のなかにわⅢ 1B)
の商品情報を取得する。BASE(独自ドメイン)。珈琲焙煎所(就労継続支援B型事業所)と試飲のできる珈琲専門店。
八千代市の「Cafeふくろう」とは別の店。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-26時点): ショップトップの16商品のうち、焙煎豆7銘柄(ブレンド1・シングル5・デカフェ1)を対象とする。
各銘柄は200gと400gが別商品登録のため、最小重量の200gを代表とした(400gは重複のため除外)。
ドリップバッグ5個セット・ギフトセットは除外。商品ページは「豆(200g)」と「粉(中挽200g)」の選択式で、
豆のままの価格(粉も同額)を採用する。
商品名は商品ページのタイトルから「200g」と「(コーヒー豆・粉)」を除いたもの。
価格・在庫・説明・ロースト・精製方法は商品ページから取得する。

【在庫について】
購入ページのバリエーション(豆/粉)のうち豆の在庫が「在庫なし」なら完売とする。

【住所について】
特定商取引法に基づく表記(/law)の事業者所在地(〒273-0044 千葉県船橋市行田1-45-17 塚田のなかにわⅢ 1B)を採用。

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
    "name": "ふくろう珈琲",
    "url": "https://netshop.fukuroucoffee.co.jp/",
    "platform": "BASE",
    "address": "千葉県船橋市行田1-45-17 塚田のなかにわⅢ 1B",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(User-agent: * は /cart/ 等のみDisallow。python-requests/curl等は個別にDisallowのため識別UAを使用、間隔5秒以上)",
    "source_note": "BASE独自ドメイン https://netshop.fukuroucoffee.co.jp/ (トップ・/law)と各商品ページ、公式 https://fukuroucoffee.co.jp/ (店舗・注文焙煎の記載)を2026-10-26に確認。ショップ内に更新日の表示なし",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://netshop.fukuroucoffee.co.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.5

# id: 200g商品の商品ID / name: 表示名 / category: Noneなら自動判定 / blend: ブレンドの構成国(商品説明)
ITEMS = [
    {"id": "144080246", "name": "オリジナルブレンド", "blend": ["ペルー", "グアテマラ", "エチオピア"]},
    {"id": "144290742", "name": "エチオピア コンガ アメデラロ"},
    {"id": "144292645", "name": "ブラジル アマレロブルボン アルコイリス"},
    {"id": "144291624", "name": "ペルー カハマルカ チリノス"},
    {"id": "144300880", "name": "グァテマラ アンティグア レタナ イエローブルボン"},
    {"id": "144080563", "name": "インドネシア マンデリン ブルーバタック"},
    {"id": "150528828", "name": "【デカフェ】エチオピア G2 シダモ", "category": "デカフェ", "origin": "エチオピア"},
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_PATTERN = re.compile(
    r'<p class="cot-itemOrder-variationName"[^>]*>([^<]*)</p>\s*'
    r'(?:<p class="cot-itemOrder-variationStock"[^>]*>([^<]*)</p>)?'
)
GROUND_KEYWORDS = ("粉", "挽", "ドリップ")
ROAST_PATTERN = re.compile(r"【ロースト】\s*(極深煎|中深煎|深煎|中浅煎|浅煎|中煎)")
PROCESS_PATTERN = re.compile(r"【精製方法】\s*([^\s、。【(（]+)")


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
    desc = re.sub(r"\s+", " ", raw_desc).lstrip("●").strip()[:400] if desc_m else None
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
    if process and parsed["category"] == "ストレート":
        # ブレンド(複数の精製方法が混在)・デカフェ(脱カフェイン処理の記述)には適用しない
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
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
    with open("data_fukuroucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukuroucoffee.json に出力しました")


if __name__ == "__main__":
    main()
