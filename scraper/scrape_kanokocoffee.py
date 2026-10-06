# -*- coding: utf-8 -*-
"""
scrape_kanokocoffee.py

自家焙煎珈琲屋 花野子(cafe-kanoko.shop-pro.jp、カラーミーショップ)の商品情報を取得する。
静岡県沼津市今沢383-1。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全29商品(一覧4ページ)のうち、焙煎豆(ストレート・ブレンド)の
19商品を対象とする。ドリップパック箱入りセット・お菓子セット・保存缶セット・ギフト・
アクア/ブレーゴ/ドルチェ(ドリップパック等のセット)は除外した。「ブラジル・ショコラ」は
中煎りと中深煎りが別商品のため両方収録する。

【文字コード】EUC-JP(実データ確認済み)。

【価格・重量・在庫】
バリアントは「豆のまま(100g単位)/挽き(100g単位)/ドリップパック/ドリップパック個包装」。
「豆のまま(100g単位)」の税込価格を100gあたりの価格として採用する。stock_numは全商品None
(在庫管理なし)で、一覧にも品切れ表示は無かった(実データ確認済み)ため、「SOLD OUT」
「売り切れ」の文言があれば完売、無ければ販売中とする。

【焙煎度・精製方法について】
焙煎度は商品名(ブラジル・ショコラ)または説明文中の「中深まで煎りあげる」「深煎りで仕上げています」
のような記述がある場合のみ取得し、記載の無い商品はNone。精製方法も説明文に明記されている場合のみ
(ハニー製法・水洗処理・スマトラ式)取得する。

【住所】特定商取引法表記(/?mode=sk)で「静岡県沼津市今沢383-1」を確認済み。

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
    "name": "自家焙煎珈琲屋 花野子",
    "url": "https://cafe-kanoko.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "静岡県沼津市今沢383-1",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(shop-pro.jp共通。/secure/等以外は制限なし。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cafe-kanoko.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# 対象の焙煎豆(商品ID)。一覧(全29件)を確認して選定した。
TARGET_PIDS = [
    "77199066",   # 花野子ブレンド
    "77199178",   # イタリアンブレンド
    "77196655",   # マイルドブレンド
    "77197714",   # マラウィ・ゲイシャ
    "77195510",   # モカ・アルマッカ No.9
    "77199159",   # マンデリン・ブルーバタック
    "77199144",   # インディア AP AA
    "77199117",   # ケニアAA
    "77199038",   # ニューギニアAA
    "77197772",   # コロンビア・スプレモ・ピネローズ
    "77197734",   # コスタリカSHB
    "77196596",   # コスタリカ・グレースハーニー
    "77197695",   # タンザニアAA TOP リビングストーン
    "77197024",   # エチオピア・イリガチャフG1
    "77197001",   # グアテマラ・サンタバーバラ
    "77196712",   # 東ティモール レテフォホ 有機
    "77195613",   # メキシコ有機
    "77195587",   # ブラジル・ショコラ 中煎り
    "185999653",  # ブラジル・ショコラ 中深煎り
]

# 商品名の国名表記が coffee_parser の辞書にないものを明示する(商品名・説明文から確認済み)
ORIGIN_OVERRIDES = {
    "77197714": "マラウイ",          # マラウィ・ゲイシャ
    "77195510": "イエメン",          # 説明文「イエメン産のモカ」(マタリ)
    "77199144": "インド",            # インディア AP AA
    "77199038": "パプアニューギニア",  # ニューギニアAA
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
ROAST_PATTERN = re.compile(r"(中浅|中深|浅|中|深)(?:煎り|まで煎)")
ROAST_MAP = {"中浅": "中浅煎り", "中深": "中深煎り", "浅": "浅煎り", "中": "中煎り", "深": "深煎り"}
# 説明文に明記されている精製方法のキーワード(ここに無い商品はNone)
DESC_PROCESS_MAP = {"ハニー製法": "ハニー", "水洗処理": "ウォッシュド", "スマトラ式": "スマトラ式"}


def fetch(url: str) -> str:
    last = None
    for _ in range(4):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "euc-jp"
            return resp.text
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = re.sub(r"\s+", " ", (product.get("name") or "")).strip()

    soup = BeautifulSoup(html_text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    desc_el = soup.select_one("div.product_description")
    desc_full = desc_el.get_text("", strip=True) if desc_el else ""
    # 「ご購入は、豆のまま…」以降は購入方法の定型文なので除く
    desc = re.sub(r"\s+", " ", desc_full.split("ご購入は")[0]).strip() or None

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "raw_name" if pid != "77195510" else "product_description"
        elif not parsed["origin_country"] and desc:
            country = detect_country_name(desc)
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, None)

    # 説明文中の複数キーワードのうち、より具体的なもの(ハニー製法 > スマトラ式 > 水洗処理)を優先する
    # (コスタリカ・グレースハーニーは「水洗処理設備を所有」とも書かれるが実際の製法はハニー製法)
    process_m = next((re.search(k, desc or "") for k in ("ハニー製法", "スマトラ式", "水洗処理") if re.search(k, desc or "")), None)
    if process_m and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(DESC_PROCESS_MAP[process_m.group(0)])
    elif parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(parsed["processing_method"])

    roast_m = ROAST_PATTERN.search(title) or ROAST_PATTERN.search(desc or "")
    roast_level = ROAST_MAP[roast_m.group(1)] if roast_m else None

    variants = product.get("variants", [])
    bean_variant = next((v for v in variants if "豆のまま" in (v.get("option1_value") or "")), None)
    price = bean_variant.get("option_price_including_tax") if bean_variant else product.get("sales_price_including_tax")

    stock_num = product.get("stock_num")
    page_text = soup.get_text(" ", strip=True)
    sold_out = (isinstance(stock_num, int) and stock_num <= 0) or bool(re.search(r"SOLD\s*OUT|売り切れ", page_text, re.I))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc[:400] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
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
    with open("data_kanokocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kanokocoffee.json に出力しました")


if __name__ == "__main__":
    main()
