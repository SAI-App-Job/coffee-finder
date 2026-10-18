# -*- coding: utf-8 -*-
"""
scrape_capimecoffee.py

CAPIME coffee(カピン珈琲、山口県山口市大内問田3丁目2-41、公式 https://capime-coffee.com/)の
商品情報を取得する。BASE(ストア https://capimecoffee.base.shop/ )。

【対象商品について】
実データ確認済み(2026-10-15): BASEの「珈琲豆」カテゴリ(/categories/7191354、2ページ分)から、
ブレンド5種(CAPIME blend / música blend / CLASSIC blend / BAROQUE blend / 中也ブレンド珈琲)と
シングル13種(デカフェ1種を含む)の計18種を対象とする。全商品100g。
除外: 定期便(subscription)、ドリップバッグ、水出珈琲、ギフト(贈り物)セット、包装・紙袋、
和菓子(羊羹・干菓子)、珈琲道具、古物。
商品名・産地・精製は商品ページの表記を確認したうえで下のITEMSに明示している。価格・在庫
(item_purchasability)・説明(og:description)は商品ページから取得する。
特定商取引法に基づく表記(/law)の所在地: 〒753-0241 山口県山口市大内問田3丁目2-41。

【アクセス間隔について】
BASEは連続アクセスで429を返すため、リクエスト間隔を5秒以上空ける。429の場合は待機を延ばして再試行する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import normalize_processing_method

SHOP_INFO = {
    "name": "CAPIME coffee",
    "url": "https://capimecoffee.base.shop/",
    "platform": "BASE",
    "address": "山口県山口市大内問田3丁目2-41",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(python-requests/curl等は個別にDisallow、User-agent: *は許可。識別可能なUser-Agentを使用)",
    "source_note": "BASEストア(https://capimecoffee.base.shop/)の珈琲豆カテゴリと各商品ページ、特定商取引法に基づく表記(/law)を2026-10-15に確認",
    "last_verified_at": "2026-10-15",
}

BASE_URL = "https://capimecoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類, 産地, 精製(商品ページの表記), 焙煎度)
ITEMS = [
    ("135120601", "CAPIME blend", 100, "ブレンド", None, None, None),
    ("135120664", "música blend", 100, "ブレンド", None, None, None),
    ("135120724", "CLASSIC blend", 100, "ブレンド", None, None, None),
    ("135120782", "BAROQUE blend", 100, "ブレンド", None, None, None),
    ("135120470", "《中也ブレンド珈琲》", 100, "ブレンド", None, None, None),
    ("135124396", "IBRAHIM MOKHA", 100, "ストレート", "イエメン", "ナチュラル", None),
    ("135124275", "MUNIR MOKHA", 100, "ストレート", "イエメン", "ナチュラル", None),
    ("135124086", "FRENCH MANDHELING", 100, "ストレート", "インドネシア", "スマトラ式", "フレンチロースト"),
    ("135121356", "PEABERRY CLASSICO", 100, "ストレート", None, "ウォッシュド", None),
    ("135121296", "Ethiopia G1 Guji Uraga", 100, "ストレート", "エチオピア", "ナチュラル", None),
    ("135121237", "Ethiopia YIRGACHEFFE KONGA", 100, "ストレート", "エチオピア", "ウォッシュド", None),
    ("135121153", "TANZANIA AA NgoroNgoro Kongoni washed", 100, "ストレート", "タンザニア", "ウォッシュド", None),
    ("135121076", "Costa Rica Jaguar Honey", 100, "ストレート", "コスタリカ", "ハニー", None),
    ("135121009", "GUATEMALA Antigua Dorado SHB Washed", 100, "ストレート", "グアテマラ", "ウォッシュド", None),
    ("135120961", "MYANMAR hornbill coffee red honey", 100, "ストレート", "ミャンマー", "ハニー", None),
    ("135120898", "COLOMBIA Sierra Nevada fair trade", 100, "ストレート", "コロンビア", "ウォッシュド", None),
    ("135120850", "KENYA SIMBA", 100, "ストレート", "ケニア", "ウォッシュド", None),
    ("135120293", "【DECAF】 Ethiopia Sidamo washed", 100, "ストレート", "エチオピア", "ウォッシュド", None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def fetch_item_page(item_id: str) -> str:
    url = f"{BASE_URL}/items/{item_id}"
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"[warn] 429: item_id={item_id} {wait}秒待機して再試行")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    raise requests.RequestException(f"429が続いたため取得を断念: {url}")


def build_record(item_id, name, weight_g, category, origin, process, roast_level) -> dict:
    html_text = fetch_item_page(item_id)
    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": "shop_page" if origin else None,
        "designated_brand": None,
        "processing_method": normalize_processing_method(process) if process else None,
        "grade": None,
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": [],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, item in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            records.append(build_record(*item))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item[0]} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_capimecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_capimecoffee.json に出力しました")


if __name__ == "__main__":
    main()
