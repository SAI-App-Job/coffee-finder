# -*- coding: utf-8 -*-
"""
scrape_mahirocoffeeroastery.py

MAHIRO COFFEE ROASTERY(https://mahirocoffee.official.ec/、東京都品川区大崎1-20-8 INOビル1F)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-25時点): BASE全82件のうち100g単位の焙煎豆23銘柄(ブレンド5・デカフェ1・シングル17。200gは同銘柄の大容量なので100gを代表)。ドリップバッグ・アパレルは除外。果実・ラム酒・シナモンを加えた銘柄(ネパールラム、コロンビア ラズベリー/パッションフルーツ/ハイビスカス/リサラルダ・ミラン Agi Culturing、シナモン BLEND)はインフューズド扱いで除外。
商品名・重量・分類・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上空ける。
"""

import json
import re
import time
import html as htmllib

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "MAHIRO COFFEE ROASTERY",
    "url": "https://mahirocoffee.official.ec/",
    "platform": "BASE",
    "address": "東京都品川区大崎1-20-8 INOビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASE(official.ec、https://mahirocoffee.official.ec/)の商品一覧と各商品ページ、公式サイト https://mahiro-coffee.com/ (「大崎駅徒歩1分…本格自家焙煎コーヒー豆を販売」)を2026-10-25に確認。住所は食べログ・公式SHOP表記。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://mahirocoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.0
DEFAULT_WEIGHT_G = 100

# (商品ID, 商品名, 分類(None=自動判定), 産地の上書き(None=商品名から判定), 焙煎度(None=商品ページから判定))
ITEMS = [
    ('97217256', 'MAHIRO BLEND', 'ブレンド', None, None),
    ('97217421', '大崎 BLEND', 'ブレンド', None, None),
    ('156574851', '秋色ブレンド', 'ブレンド', None, None),
    ('103988203', 'あわいろブレンド', 'ブレンド', None, None),
    ('97217722', 'カリブブレンド', 'ブレンド', None, None),
    ('97218196', 'デカフェコーヒー', 'デカフェ', 'コロンビア', None),
    ('152890981', 'ケニア トマトレッド', None, None, None),
    ('152659733', 'インドネシア マンデリンブルーバタック', None, None, None),
    ('152659657', 'ウガンダ アフリカンムーンジャッカル', None, 'ウガンダ', None),
    ('152659632', 'エチオピア モカイルガチェフェG1アメデラロ', None, None, None),
    ('152659571', 'エチオピア モカイルガチェフェG1ゲデブ', None, None, None),
    ('152659540', 'エチオピア モカイルガチェフェG1コチャレ', None, None, None),
    ('152659471', 'エチオピア モカイルガチェフェG1コンガ', None, None, None),
    ('152659416', 'コスタリカ ジャガープロジェクト', None, None, None),
    ('152891195', 'コロンビア Cattura Nitro', None, None, None),
    ('152659255', 'コロンビア JOKERナリーニョラウニオン', None, None, None),
    ('152659189', 'コロンビア SL28ケブラディタス', None, None, None),
    ('152659160', 'コロンビア ゲイシャSAKE', None, None, None),
    ('153120014', 'ネパール アナエロビコ', None, 'ネパール', None),
    ('152658906', 'ネパール ピーベリー', None, 'ネパール', None),
    ('152658341', 'ブラジル サントス Dried on Tree', None, None, None),
    ('152658249', 'ベトナム バレルエイジド', None, None, None),
    ('150592131', 'ミャンマー オレンジサンシャイン', None, None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORDS = ["中浅煎り", "中深煎り", "浅煎り", "深煎り", "中煎り"]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def page_text(html_text: str) -> str:
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", txt)))


def og_desc(html_text: str) -> str | None:
    m = DESC_PATTERN.search(html_text)
    return htmllib.unescape(clean(m.group(1)))[:400] if m else None


def extract(html_text: str, name: str) -> dict:
    mm = DESC_PATTERN.search(html_text)
    full = htmllib.unescape(clean(mm.group(1))) if mm else ""
    # 先頭の「ーーーー名称（精製）ーーーー・Features」の見出しを除いて説明文にする
    body = re.sub(r"^ー{3,}.*?ー{3,}", "", full).strip()
    body = re.sub(r"^・Features\s*", "", body)
    out = {"desc": body[:400] or None}
    # 「・Roast浅煎り【使用上の注意】」から焙煎度(複数併記「浅煎り / 深煎り」は不明扱い)
    m = re.search(r"Roast\s*([^【]*)", full)
    if m and "/" not in m.group(1):
        for w in ROAST_WORDS:
            if w in m.group(1):
                out["roast"] = w
                break
    # 「ーーーー名称（精製）ーーーー」の括弧内から精製方法
    m = re.search(r"ー{3,}[^（）]*（([^）]+)）ー{3,}", full)
    if m:
        out["processing"] = detect_processing_method(m.group(1))
    return out


def build_record(item_id: str, name: str, category_override, origin_override, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"
    extra = extract(html_text, name)

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
        if origin_override:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "raw_name"
        elif not parsed["origin_country"] and extra.get("origin"):
            parsed["origin_country"] = extra["origin"]
            parsed["origin_source"] = "description"

    processing = parsed["processing_method"] or extra.get("processing")
    roast = roast_level or extra.get("roast") or parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": extra.get("desc"),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": DEFAULT_WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, category_override, origin_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, category_override, origin_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mahirocoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mahirocoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
