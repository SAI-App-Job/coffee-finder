# -*- coding: utf-8 -*-
"""
scrape_purecastle.py

Purecastle珈琲(purecastle-shop.com、沖縄県豊見城市豊崎1-40 プロースト102号室)の
商品情報を取得する。WordPress + Welcart。

robots.txt確認済み(2026-09時点): Yoast SEO標準ブロックのみ、制限なし
(User-agent: * でDisallowなし)。

【カテゴリ一覧ページが空になる不具合について】
実データ確認済み(2026-09時点): `/item/itemgenre/<スラッグ>/`のカテゴリ別
一覧ページのうち、`regular-sale`(定期便コース)のみは静的HTMLに商品リンクが
含まれるが、`specialty`・`blend`・`standard`・`gift`・`brewer`はUser-Agentや
Cookieセッションの有無に関わらずitem-list-block(商品一覧を差し込むはずの
コンテナ)が常に空で返る(ブラウザ同等のUser-Agentでも同様、キャッシュ系の
不具合と推測されるが原因未特定)。/wp-json/にも商品用のREST型は登録されて
いない(Welcart標準の非公開カスタム投稿タイプ)。

代替として、トップページ(https://purecastle-shop.com/)に新着・注目商品として
直接リンクされている商品(実データ確認済み: 21件、regular-saleカテゴリの
9件はすべてこの21件に含まれる)と、regular-saleカテゴリ一覧ページの両方から
商品URL(/item/<ID>/)を収集する。これは全商品を完全に補償する保証はないが、
カテゴリ一覧が構造的に機能しない状況下での誠実な最善努力である。

【非コーヒー豆商品の除外について】
実データ確認済み(全21件): 定期便コース(年間コース/半年コース/お試し3ヶ月
コース、いずれもスタンダード/ブレンド/スペシャルティ各グレードの商品を
月々の定期購入用に再パッケージ化したもので、単品(1回購入)と同じ豆の
サブスクリプション契約のため重複除外)・ギフト(ブック型ギフト、感謝の黒箱
ギフト)がNON_BEAN_KEYWORDSで除外される。残り10件(ストレート8種+
自社ブレンド2種)を対象とする。

【重量バリエーションについて】
実データ確認済み: 商品詳細ページに「100グラム」「200グラム」「300グラム」
「400グラム」の4段階の`div.item-name`ブロックがあり、それぞれに対応する
`skuPrice[...]`隠しフィールドで価格が構造化されている(挽き方の選択肢は
価格に影響しない)。最小重量(100g)を代表として採用する。

【在庫状態について】
実データ確認済み: 静的HTMLから信頼できる構造化された品切れフラグを
特定できなかった(JSアラート文言のみで、実際の商品ごとの在庫有無を示す
ものではない)。商品名のテキストのみで在庫状態を判定する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Purecastle珈琲",
    "url": "https://purecastle-shop.com/",
    "platform": "WordPress + Welcart",
    "address": "沖縄県豊見城市豊崎1-40 プロースト102号室",
    "prefecture": "沖縄県",
    "robots_txt_status": "許可(2026-09確認。Yoast SEO標準ブロックのみ、制限なし)",
}

BASE_URL = "https://purecastle-shop.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 実データ確認済み(理由はdocstring参照)
NON_BEAN_KEYWORDS = ["コース", "ギフト"]

ITEM_ID_PATTERN = re.compile(r"/item/(\d+)/")
TITLE_PATTERN = re.compile(r'<div class="heading-04">\s*<h2>([^<]+)</h2>', re.DOTALL)
WEIGHT_BLOCK_PATTERN = re.compile(r'item-name">「(\d+)グラム」')
SKU_PRICE_PATTERN = re.compile(r'skuPrice\[\d+\]\[[^\]]+\]"\s*value="(\d+)"')


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_item_urls() -> list[str]:
    ids: set[int] = set()
    for url in (BASE_URL + "/", f"{BASE_URL}/item/itemgenre/regular-sale/"):
        try:
            text = fetch_text(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            continue
        ids.update(int(i) for i in ITEM_ID_PATTERN.findall(text))
    return [f"{BASE_URL}/item/{i}/" for i in sorted(ids)]


def parse_item_page(url: str) -> dict | None:
    text = fetch_text(url)
    title_m = TITLE_PATTERN.search(text)
    if not title_m:
        return None
    title = title_m.group(1).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    weights = [int(w) for w in WEIGHT_BLOCK_PATTERN.findall(text)]
    prices = [int(p) for p in SKU_PRICE_PATTERN.findall(text)]

    weight_g = None
    price = None
    if weights and prices and len(weights) == len(prices):
        # 最小重量を代表として採用(他店舗と同じ考え方)
        idx = weights.index(min(weights))
        weight_g = weights[idx]
        price = prices[idx]

    return {"raw_name": title, "price": price, "weight_g": weight_g, "product_url": url}


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    urls = collect_item_urls()

    records = []
    flavored_records = []
    for url in urls:
        try:
            item = parse_item_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if item is None:
            continue

        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_purecastle.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_purecastle.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
