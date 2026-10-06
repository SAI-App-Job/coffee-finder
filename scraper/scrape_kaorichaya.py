# -*- coding: utf-8 -*-
"""
scrape_kaorichaya.py

香茶屋(kaori-chaya.shop-pro.jp、カラーミーショップ)の商品情報を取得する。
静岡県浜松市中央区舘山寺町2543-2(特定商取引法表記で確認)。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全44商品(?mode=srh の一覧を4ページ分確認)のうち、焙煎豆
(シングルオリジン・ブレンド・デカフェ・水出し用ブレンド豆)の11商品を対象とする。
ドリップバッグ(DB)・ギフト/お試しセット・定期便・水出しアイスコーヒーパック・フィルター・
器具・講座・コーヒーミルで挽いた飲み比べ商品は除外した。

【文字コード】EUC-JP(実データ確認済み)。

【価格・重量・在庫】
全商品が「小分け(する/しない) × 豆のまま(135g)/粉にする(130g)」のバリアント構成
(実データ確認済み)。「豆のまま(135g)」の価格(税込)と重量を採用する。在庫は var Colorme の
stock_num(商品単位)で判定する(0の商品は完売。例: モンテコペイ・キズナ農園)。

【商品名・説明について】
商品ページに説明文は無く、商品名に「産地・農園・精製(W=ウォッシュド、WH=ホワイトハニー)・
焙煎度」が埋め込まれている(例: コロンビア・ビシャファティマ農園・W・シティロースト)。
産地・焙煎度は coffee_parser で商品名から取得し、W/WH のみここで精製方法に変換する。
商品名に焙煎度が無いブレンド・デカフェ・水出し用豆の焙煎度は不明のため None。

【robots.txtについて】
shop-pro.jp の他店舗と同一の記述(/secure/ 等のみ制限)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "香茶屋",
    "url": "https://kaori-chaya.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "静岡県浜松市中央区舘山寺町2543-2",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(shop-pro.jp共通。/secure/等以外は制限なし。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://kaori-chaya.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# 対象の焙煎豆(商品ID)。一覧(全44件)を確認して選定した。
TARGET_PIDS = [
    "158001903",  # ショコラブレンド
    "158001735",  # 花ブレンド
    "159636213",  # コールドブリューブレンド(水出しアイスコーヒー専用豆)
    "190800388",  # ＜カフェインレス＞エチオピア・シダモ G2・ウォッシュド
    "158001861",  # ブラジル・コクェイロ農園・ナチュラル・イエローカトゥアイ・フルシティロースト
    "158001104",  # ブラジル・コクェイロ農園・イエローカトゥアイ・ナチュラル・ミディアムロースト
    "158001815",  # コロンビア・ビシャファティマ農園・W・シティロースト
    "158001514",  # コスタリカ・ラリア・ピエサン農園・WH・ミディアムロースト
    "158000999",  # ケニア・キリニャガ・カリアイニファクトリー・シナモンロースト
    "157907438",  # エチオピア・イルガチェフェ・チェリチェレCWS・W・ライトロースト
    "158001054",  # コスタリカ・モンテコペイ・キズナ農園・WH・シナモンロースト
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 商品名中の精製方法略号(実データ確認済み: W=ウォッシュド、WH=ホワイトハニー)
PROCESS_TOKENS = {"W": "ウォッシュド", "WH": "ホワイトハニー", "CWS": "ウォッシュド"}


def fetch(url: str) -> str:
    last = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "euc-jp"
            return resp.text
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def extract_product(html_text: str) -> dict | None:
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("product")
    except json.JSONDecodeError:
        return None


def pick_variant(variants: list[dict]) -> dict | None:
    """「豆のまま」バリアントのうち、小分けしない・最小重量のものを代表にする。"""
    def weight(v):
        m = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        return int(m.group(1)) if m else 10**9

    beans = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    if not beans:
        return None
    return min(beans, key=lambda v: (weight(v), "小分けしない" not in (v.get("option1_value") or "")))


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    product = extract_product(fetch(url))
    if not product:
        return None
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return None
    parsed = apply_category_hint_fallback(parsed, None)

    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    if not parsed["processing_method"]:
        for token in re.split(r"[・\s/]+", title):
            if token in PROCESS_TOKENS:
                parsed["processing_method"] = normalize_processing_method(PROCESS_TOKENS[token])
                break

    variant = pick_variant(product.get("variants", []))
    weight_m = WEIGHT_PATTERN.search((variant or {}).get("option2_value") or "")
    stock_num = product.get("stock_num")
    sold_out = isinstance(stock_num, int) and stock_num <= 0

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
        "roast_hint": None,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax") if variant else product.get("sales_price_including_tax"),
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in TARGET_PIDS:
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kaorichaya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kaorichaya.json に出力しました")


if __name__ == "__main__":
    main()
