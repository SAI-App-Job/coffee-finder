# -*- coding: utf-8 -*-
"""
scrape_corsicacoffee.py

コルシカ珈琲(CORSICA COFFEE DEVELOPMENT、公式 https://corsicacoffee.net/、ストア
https://shop.corsicacoffee.com 、香川県高松市中央町18-9)の商品情報を取得する。BASE(独自ドメイン)。

【対象商品について】
実データ確認済み(2026-10-15): ストア全20商品のうち、コーヒー豆14銘柄を対象とする。
除外: MIX2/MIX3/MIX4(100g×複数袋のセット)、定期便(CORSICA BEANS PORTER 300g)、
15th Anniversary Set(50g×2袋セット、売切れ)。
標準銘柄は150g、特別ロット・シーズナルは100g、ペルーSL9 Imagineのみ60g/100gの2商品が並ぶため
最小重量の60g(4,000円)を代表とする。「Imagine」はペルーSL9(特別ロット)とブラジル(通常100g)の
2つの別ロットがあり、別銘柄として扱う(商品名は(ペルーSL9)Imagine / Imagine)。
Fruit&Roots(item_purchasability=unpurchasable)は完売として収録する。
商品ページに焙煎度の記載は無い(Mouflon Signature Blendのみ「エスプレッソロースト」の記述)。
産地・精製は商品説明の「生産国」「生産処理」から取得する(冒頭に英語名のみの商品もあるため
ITEMSで明示)。価格・在庫・説明は商品ページ(og:description、product:price:amount、
item_purchasability)から取得する。
ストアはBASEの短時間アクセス制限(429)が厳しいため、リクエスト間隔を長め(4秒)にし、
429時は待機して再試行する(User-Agent変更等の回避は行わない)。
"""

import html as htmllib
import json
import re
import time

import requests

from coffee_parser import parse_product, normalize_processing_method

SHOP_INFO = {
    "name": "コルシカ珈琲",
    "url": "https://shop.corsicacoffee.com/",
    "platform": "BASE(独自ドメイン)",
    "address": "香川県高松市中央町18-9",
    "prefecture": "香川県",
    "robots_txt_status": "未確認(BASE標準構成。識別可能なUser-Agent・長めの間隔でアクセス)",
}

BASE_URL = "https://shop.corsicacoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 4
RETRY_WAIT_SECONDS = 60
MAX_RETRIES = 5

# (商品ID, 商品名, 重量(g), 分類(ストレート/ブレンド), 産地, 焙煎度ヒント)
ITEMS = [
    ("127196312", "#9Dream", 100, "ストレート", "エチオピア", None),
    ("156709790", "(ペルーSL9)Imagine", 60, "ストレート", "ペルー", None),
    ("67604567", "Imagine", 100, "ストレート", "ブラジル", None),
    ("25289021", "Bloomin'", 150, "ストレート", "タンザニア", None),
    ("26453670", "Strange Fruit", 150, "ストレート", "ルワンダ", None),
    ("26559514", "Decaf", 150, "ストレート", "メキシコ", None),
    ("26567999", "Here Comes The Sun", 150, "ストレート", "エルサルバドル", None),
    ("27161882", "Across The Universe", 150, "ストレート", "エチオピア", None),
    ("27759369", "Terra Nova", 150, "ストレート", "グアテマラ", None),
    ("28678553", "Fruit&Roots", 150, "ストレート", "エチオピア", None),
    ("28678945", "Day Tripper", 150, "ストレート", "コスタリカ", None),
    ("37080304", "Mouflon Signature Blend", 150, "ブレンド", None, "エスプレッソロースト"),
    ("62471668", "Afterdark", 150, "ストレート", "グアテマラ", None),
    ("67402002", "Mt.Kenya", 150, "ストレート", "ケニア", None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PROCESS_PATTERN = re.compile(r"生産処理\s*[:：]?\s*(.+?)(?:BLACK LABEL|オリジン|※|$)")


def fetch_item(item_id: str) -> str:
    for attempt in range(MAX_RETRIES):
        resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            print(f"[wait] 429: item_id={item_id} {RETRY_WAIT_SECONDS}秒待機して再試行")
            time.sleep(RETRY_WAIT_SECONDS)
            continue
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    raise requests.RequestException(f"429が続いたため断念: {item_id}")


def build_record(item_id: str, name: str, weight_g: int, category: str, origin: str | None, roast_hint: str | None) -> dict:
    html_text = fetch_item(item_id)
    desc_m = DESC_PATTERN.search(html_text)
    desc_raw = htmllib.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", desc_raw).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    processing = None
    pm = PROCESS_PATTERN.search(desc_raw)
    if pm:
        processing = normalize_processing_method(pm.group(1).strip())

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": "description" if origin else None,
        "designated_brand": None,
        "processing_method": processing,
        "grade": None,
        "roast_level": None,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
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
    for item_id, name, weight_g, category, origin, roast_hint in ITEMS:
        try:
            records.append(build_record(item_id, name, weight_g, category, origin, roast_hint))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_corsicacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_corsicacoffee.json に出力しました")


if __name__ == "__main__":
    main()
