# -*- coding: utf-8 -*-
"""
scrape_logcoffeeroasters.py

LOG COFFEE ROASTERS(https://logcoffee.thebase.in/、山口県山口市中市町4-14)の商品情報を取得する。BASE。

【店舗の確認】
公式 https://log-coffee-roasters.com/ に「スペシャルティコーヒー専門の自家焙煎コーヒーショップ」、
/concept に所在地(山口市中市町4-14)・営業時間 11:00〜19:00・定休日月曜の記載。
住所は特商法(https://logcoffee.thebase.in/law)とも一致(2026-11-01確認)。

【対象商品について】
実データ確認済み(2026-11-01時点): COFFEE BEANS(100g / 200gカテゴリ)に同一銘柄が100gと200gで別商品として並ぶため、
最小重量の100g商品11銘柄(ブレンド2・シングル9、デカフェ含む)を代表にする。200g商品、ドリップパック、
おまかせセット(100g×2・3種)、ギフト、器具、WHOLE SALEは除外。
商品名・重量・焙煎度は商品ページのタイトル表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txt】
python-requests/curl等は個別にDisallow、User-agent: * では /cart/ /web_cart/ /shops/ 等のみ禁止。
本スクレイパーは識別可能な独自User-Agentを使用し、商品ページ(/items/)のみ取得、間隔5秒。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "LOG COFFEE ROASTERS",
    "url": "https://logcoffee.thebase.in/",
    "platform": "BASE",
    "address": "山口県山口市中市町4-14",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(User-agent: * は /cart/ 等のみ禁止。python-requests/curl等は個別に禁止のため識別可能なUser-Agentを使用)",
    "source_note": "https://logcoffee.thebase.in/ の商品ページ・/lawと公式 https://log-coffee-roasters.com/ を2026-11-01に確認。"
                   "公式トップに「スペシャルティコーヒー専門の自家焙煎コーヒーショップ」、/conceptに所在地・営業時間・定休日の記載があり実店舗・自家焙煎。"
                   "商品に日付表示はないが銘柄は現行。同一銘柄が100g・200gで並ぶため100gを代表に採用(セット・ドリップパック・ギフト等は除外)",
    "last_verified_at": "2026-11-01",
}

BASE_URL = "https://logcoffee.thebase.in"
REQUEST_INTERVAL_SEC = 5  # BASEは5秒以上
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度)  ※すべて100gの商品
ITEMS = [
    ("26835018", "Keyaki Blend（ケヤキ ブレンド）", 100, "ブレンド", "中深煎り"),
    ("98979240", "Kogane Blend（コガネ ブレンド）", 100, "ブレンド", "浅煎り"),
    ("27658333", "Brazil Santa Ines（ブラジル サンタ・イネス農園）", 100, None, "中深煎り"),
    ("103433330", "Brazil Rio Brilhante（ブラジル リオブリシャンテ）", 100, None, "中深煎り"),
    ("99095333", "Ethiopia Silinga（エチオピア シリンガ）", 100, None, "中深煎り"),
    ("82178979", "Kenya Chorongi（ケニア チョロンギ）", 100, None, "中深煎り"),
    ("109123405", "Colombia La Esperanza（コロンビア ラ・エスペランサ）", 100, None, "浅煎り"),
    ("29782435", "Ethiopia Yirgacheffe Konga（エチオピア イルガチェフェ コンガ）", 100, None, "浅煎り"),
    ("104458579", "Tanzania Acacia Hills（タンザニア アカシアヒルズ）", 100, None, "中煎り"),
    ("100339866", "Costa Rica Don Eli（コスタリカ ドン・エリ）", 100, None, "中煎り"),
    ("27793910", "Mexico Decafe（メキシコ デカフェ）", 100, None, "深煎り"),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
TASTING_PATTERN = re.compile(r"【Tasting Note】(.*?)(?=【Tasting Chart】|【Detail】|$)")
DETAIL_PATTERN = re.compile(r"【Detail】(.*?)(?=※配送|【Shop Brew Recipe】|$)")
DETAIL_ITEM_PATTERN = re.compile(r"(生産国|ブレンド配合比率|生産エリア|プロセス|品種|標高)[:：]\s*(.+?)(?=生産国|ブレンド配合比率|生産エリア|プロセス|品種|標高|$)")


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    full_desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip() if desc_m else ""
    tasting_m = TASTING_PATTERN.search(full_desc)
    flavor_notes = (tasting_m.group(1).strip() if tasting_m else full_desc)[:400] or None
    detail_m = DETAIL_PATTERN.search(full_desc)
    detail = dict(DETAIL_ITEM_PATTERN.findall(detail_m.group(1))) if detail_m else {}
    detail = {k: v.strip() for k, v in detail.items() if v.strip() not in ("ー", "-", "―")}
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(detail.get("生産国", "")) or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    if parsed["category"] == "ブレンド":
        # ブレンドは構成ごとにプロセスが異なるため精製方法は単一値にせず、構成をfarm_noteに残す
        parsed["processing_method"] = None
        farm_keys = ("生産国", "ブレンド配合比率", "プロセス")
    else:
        if detail.get("プロセス") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(detail["プロセス"])
        farm_keys = ("生産エリア", "品種", "標高")
    farm_note = "、".join(f"{k}: {detail[k]}" for k in farm_keys if detail.get(k)) or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
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
    for i, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_logcoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_logcoffeeroasters.json に出力しました")


if __name__ == "__main__":
    main()
