# -*- coding: utf-8 -*-
"""
scrape_chitose105.py

自家焙煎珈琲 ちとせ105(chitose105.com、静岡県熱海市泉127-19、焙煎豆の小売り・卸売り、カフェ・テイクアウトあり)
のオンラインショップ(https://chitose105.handcrafted.jp/、BASE)の商品情報を取得する。

【店舗発見の経緯】
静岡県の再調査の新規発掘で発見。公式サイトはWordPressで、販売はBASE(handcrafted.jpドメイン)。
熱海の「coffee house 茶々」(登録済)とは別店。

【対象商品について】
実データ確認済み(2026-10時点): BASE全17商品(/items/all)すべてが自家焙煎のコーヒー豆
(シングル13・ブレンド4)。ドリップバッグ・セット・器具の取り扱いなし。各商品は100g。
商品ID一覧は /items/all から取得し、商品名(日本語部分)・価格・在庫・説明は商品ページ
(og:title / product:price:amount / item_purchasability / og:description)から取得する。
焙煎度は、説明文中の「＜中煎り＞~お勧め(店頭販売)」の記載をおすすめ焙煎度として採用する
(ブレンドなど記載のない商品はNone)。購入時に焙煎度・挽き方を選択できる。

【robots.txtについて】
実データ確認済み(2026-10-26): 他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、
User-agent: *では許可)。識別可能な独自User-Agentを使用し、リクエスト間隔は5秒。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲 ちとせ105",
    "url": "https://chitose105.handcrafted.jp/",
    "platform": "BASE",
    "address": "静岡県熱海市泉127-19",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://chitose105.handcrafted.jp/items/all)の全17商品と各商品ページを2026-10-26に確認。住所は公式サイト https://chitose105.com/ のフッター。公式サイトは2026年10月の営業スケジュールを掲載しており更新は新しい。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://chitose105.handcrafted.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5.0

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ITEM_LINK_PATTERN = re.compile(r'href="https://chitose105\.handcrafted\.jp/items/(\d+)"')
RECOMMENDED_ROAST = re.compile(r"＜([^＞]*煎り)＞\s*~?[^＜]{0,25}?お勧め")
WEIGHT_CUT = re.compile(r"\s*100\s*[gｇ].*$", re.S)


def get(url: str) -> requests.Response:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp


def list_item_ids() -> list[str]:
    resp = get(f"{BASE_URL}/items/all")
    ids: list[str] = []
    for m in ITEM_LINK_PATTERN.finditer(resp.text):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def build_record(item_id: str) -> dict | None:
    resp = get(f"{BASE_URL}/items/{item_id}")
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: item_id={item_id} ({resp.status_code})")
        return None
    text = resp.text
    title_m = TITLE_PATTERN.search(text)
    if not title_m:
        return None
    title = html.unescape(title_m.group(1)).split(" | ")[0]
    # 「日本語名 100g English name 100g」の日本語名の部分だけを商品名にする
    name = WEIGHT_CUT.sub("", title).replace("”", '"').replace("“", '"').replace("　", " ").strip()
    name = re.sub(r"\s+", " ", name)

    desc_m = DESC_PATTERN.search(text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(text)
    pur_m = PURCHASABILITY_PATTERN.search(text)
    sold_out = bool(pur_m) and pur_m.group(1) == "unpurchasable"
    roast_m = RECOMMENDED_ROAST.search(desc or "")

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

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_m.group(1) if roast_m else None,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in list_item_ids():
        try:
            rec = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: item_id={item_id} ({e})")
            continue
        if rec is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_chitose105.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chitose105.json に出力しました")


if __name__ == "__main__":
    main()
