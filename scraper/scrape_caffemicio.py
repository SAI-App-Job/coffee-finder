# -*- coding: utf-8 -*-
"""
scrape_caffemicio.py

caffè micio(https://caffemicio.theshop.jp/、京都府京都市左京区浄土寺下南田町27 錦林ハウス3)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(京都府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全30商品のうち、100gの豆14銘柄(オーガニック・フェアトレード中心)。ドリップバッグ・水出しパック・お試しセット・おすすめセット・定期便・サスペンドコーヒー・1kg大袋(産地をプルダウンで選ぶ業務用)を除いた。デカフェ エチオピアは焙煎度違い(深煎り/中煎り)の別ページのため両方を収録。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)は商品ページから取得する。説明は、og:descriptionが商品によって店舗共通の紹介文になるため、
商品ページ本文(「詳細を見る」〜「内容量」の間)から取得する(本文が「詳細はしばらくお待ちください」のみの商品はnull)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "caffè micio",
    "url": "https://caffemicio.theshop.jp/",
    "platform": "BASE",
    "address": "京都府京都市左京区浄土寺下南田町27 錦林ハウス3",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://caffemicio.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('58243382', 'デカフェ エチオピア マウンテンウォータープロセス 深煎り', 100, None, '深煎り'),
    ('27562524', 'デカフェ エチオピア マウンテンウォータープロセス 中煎り', 100, None, '中煎り'),
    ('16091427', 'タンザニア ルカニ村 キリマンジャロ', 100, None, '中煎り'),
    ('153930516', 'パプアニューギニア マッドマンコーヒー 深煎り', 100, None, '深煎り'),
    ('54549269', 'ブラジル ダテーラ農園 サンライズ 深煎り', 100, None, '深煎り'),
    ('142323434', 'エチオピア モカ ジマ ゲラ農園 G1 ウォッシュ 中煎り', 100, None, '中煎り'),
    ('106554849', 'ペルー マチュピチュ 中深煎り', 100, None, '中深煎り'),
    ('125369313', 'インド ポアブス農園 浅煎り', 100, None, '浅煎り'),
    ('856360', '東ティモール ロロサエ 中深煎り', 100, None, '中深煎り'),
    ('16091397', 'メキシコ マヤビニック 中煎り', 100, None, '中煎り'),
    ('46322009', 'メキシコ Nuu Itee (ヌーイテエ) 中煎り', 100, None, '中煎り'),
    ('58901485', 'タンザニア ジェニュイン キリマンジャロ 中煎り', 100, None, '中煎り'),
    ('58635498', 'No Nukes Blend 深煎りブレンド', 100, 'ブレンド', '深煎り'),
    ('58143753', 'フィリピン コーディリエラ', 100, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'58143753': 'フィリピン'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


DETAIL_PATTERN = re.compile(r"詳細を見る (.*?) (?:内容量|-{4,})")


def extract_description(html_text: str, desc_m) -> str | None:
    """商品ページ本文(「詳細を見る」〜「内容量」の間)の味わい説明を取得する。
    og:descriptionは商品によって店舗共通の紹介文になるため、本文から取る。
    本文が「(詳細はしばらくお待ちください)」のみの商品はNone。"""
    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.select_one("[class*=item-detail_container]")
    if container:
        body = re.sub(r"\s+", " ", container.get_text(" ", strip=True))
        m = DETAIL_PATTERN.search(body)
        if m:
            text = m.group(1).strip()
            return None if text.startswith("(詳細はしばらく") or text.startswith("（詳細はしばらく") else text[:400]
    if desc_m:
        text = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()
        if not text.startswith("京都・左京のコーヒーロースター") and not text.startswith("（詳細はしばらく"):
            return text[:400]
    return None


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = extract_description(html_text, desc_m)
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
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
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
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        time.sleep(1.0)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_caffemicio.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_caffemicio.json に出力しました")


if __name__ == "__main__":
    main()
