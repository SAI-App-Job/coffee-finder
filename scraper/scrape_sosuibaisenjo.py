# -*- coding: utf-8 -*-
"""
scrape_sosuibaisenjo.py

疏水焙煎所/KIKKAKEKKO(https://shop.nuts-to-mamenoki.com/、滋賀県大津市大門通4-3)の商品情報を取得する。
BASE(独自ドメイン)。食べログ上の店名は「ナッツと豆の木焙煎所」(同住所・同URL)。

【店舗発見の経緯】
滋賀県・奈良県の新規発掘で発見(2026-11-01)。

【対象商品について】
実データ確認済み(2026-11-01時点): ALL ITEMに24点=12銘柄×(168g/252g)。各銘柄の最小重量168gを代表とする。
ナッツ類のカテゴリは対象外。「コロンビア パッションフルーツ」はパッションフルーツを用いた
カーボニックマセレーション(果実を加える製法=インフューズド)のため除外。
価格・在庫(item_purchasability)・説明(og:description)・推奨焙煎度は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では許可)。
本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "疏水焙煎所/KIKKAKEKKO",
    "url": "https://shop.nuts-to-mamenoki.com/",
    "platform": "BASE",
    "address": "滋賀県大津市大門通4-3",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE公式ショップ(https://shop.nuts-to-mamenoki.com/)の商品ページを2026-11-01に確認。"
                   "住所は特定商取引法に基づく表記(運営:合同会社キッカケッコ)。食べログ上の店名は「ナッツと豆の木焙煎所」(同住所)。"
                   "各銘柄の最小重量168gを代表とし、252g・ナッツ類・パッションフルーツ(果実を用いた発酵)は除外。",
    "last_verified_at": "2026-11-01",
}

BASE_URL = "https://shop.nuts-to-mamenoki.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.5  # BASEは5秒以上

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定)) 168g版のみ
ITEMS = [
    ("141419768", "コロンビア SP", 168, None),
    ("141419872", "コロンビア SPデカフェ", 168, "デカフェ"),
    ("141419818", "JOKER／コロンビア", 168, None),
    ("141416683", "グアテマラSHB イエローブルボン", 168, None),
    ("141415351", "ミャンマー G1 オレンジサンシャイン", 168, None),
    ("141415252", "エチオピア イルガチェフェG1 コチャレ 7Days", 168, None),
    ("141420633", "AFRICAN MOON JACKAL ルウェンゾリ", 168, None),
    ("141420523", "タンザニア キリマンジャロ", 168, None),
    ("141415788", "コロンビア ウシュウシュ", 168, None),
    ("141415496", "ニカラグア バニラレモネード", 168, None),
    ("141415400", "コスタリカ FSHB ラクティック アナエロビック・ハニー", 168, None),
]

ORIGIN_OVERRIDES = {"141420633": "ウガンダ"}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"推奨焙煎度\s*[：:/／]?\s*([^■【\s]+)")
ROAST_MAP = {"シティロースト": "シティロースト", "ハイロースト": "ハイロースト", "フルシティロースト": "フルシティロースト"}


def build_record(item_id, name, weight_g, category_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc_full = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    # 推奨焙煎度が1つに決まる場合のみ焙煎度として採用(「ハイローストorシティロースト」等は不明扱い)
    roast = None
    rm = ROAST_PATTERN.search(desc_full)
    if rm and rm.group(1) in ROAST_MAP:
        roast = ROAST_MAP[rm.group(1)]

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
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
            parsed["origin_source"] = "raw_name"

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
        "flavor_notes": desc_full[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products():
    records = []
    for i, (item_id, name, weight_g, category_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            record = build_record(item_id, name, weight_g, category_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sosuibaisenjo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sosuibaisenjo.json に出力しました")


if __name__ == "__main__":
    main()
