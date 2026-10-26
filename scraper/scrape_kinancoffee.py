# -*- coding: utf-8 -*-
"""
scrape_kinancoffee.py

kinan coffee(https://kinancafe.base.shop/、大阪府摂津市三島2-1-13)の商品情報を取得する。BASE(https://kinancafe.base.shop)。

【店舗発見の経緯】
大阪府の新規発掘調査(2026-10-26)で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全14商品のうち自家焙煎のコーヒー豆100g単品7銘柄(シングルオリジン6・デカフェ1)。お試しセット・ドリップパック・水出しパック・飲み比べセット(2種/3種)・だしスープ・寄付チケットは除外。有機/無農薬のシングルオリジンのみの品ぞろえ。
商品名・重量・産地・分類は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)・
焙煎度(ページ内の「■ロースト」等の表記。ITEMSで明示した場合はそちらを優先)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "kinan coffee",
    "url": "https://kinancafe.base.shop/",
    "platform": "BASE",
    "address": "大阪府摂津市三島2-1-13",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://kinancafe.base.shop/about (「大阪府摂津市を拠点とする自家焙煎珈琲店」)、/law (事業者所在地 摂津市三島2-1-13、不定休)、ごーがいネット摂津 https://settsu.goguynet.jp/2024/08/25/kinan-coffee/ (2024年7月29日に自宅ガレージでテイクアウト店オープン、「自家焙煎珈琲 kinan coffeeです」)、各商品ページを2026-10-26に確認。店頭はテイクアウト窓口(営業日はInstagramで告知)、焙煎機の機種・設置場所は未確認。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://kinancafe.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneならページから判定), 産地(ブレンドはNone))
ITEMS = [('81844359', 'インドネシア トラジャ ランテカルア', 100, None, 'シティロースト', 'インドネシア'),
    ('137362657', 'コロンビア シエラネバダ ラ・ミエル', 100, None, 'シティロースト', 'コロンビア'),
    ('132344321', '東ティモール エルメラ', 100, None, 'シティロースト', '東ティモール'),
    ('106286026', 'コスタリカ サンタルシア農園 ナチュラル', 100, None, 'シティロースト', 'コスタリカ'),
    ('92291777', 'タンザニア キゴマ', 100, None, 'シティロースト', 'タンザニア'),
    ('82431153', 'エチオピア シダマ G-1', 100, None, 'ハイロースト', 'エチオピア'),
    ('128374969', 'メキシコ チアパス デカフェ(天然水抽出)', 100, 'デカフェ', 'ハイロースト', 'メキシコ')]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
DISCOUNT_PATTERN = re.compile(r"¥\s*([\d,]+)\s*\d+%\s*OFF\s*¥\s*([\d,]+)")
ROAST_PATTERNS = [
    re.compile(r"■\s*ロースト\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)"),
    re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)に(?:仕上げ|焙煎)"),
]


def page_text(html_text: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t))


def build_record(item_id: str, name: str, weight_g: int, category_override, roast_override, origin) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        print(f"[warn] HTTP {resp.status_code}: item_id={item_id}")
        return None
    html_text = resp.text
    text = page_text(html_text)

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    disc_m = DISCOUNT_PATTERN.search(text)
    if disc_m:  # 割引表示(例: ¥1,200 10%OFF ¥1,080)がある場合は割引後の販売価格
        price = int(disc_m.group(2).replace(",", ""))
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    roast = roast_override
    if not roast:
        for pat in ROAST_PATTERNS:
            m = pat.search(text)
            if m:
                roast = m.group(1)
                break

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
        if origin:
            parsed["origin_country"] = origin
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
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL_SEC)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kinancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kinancoffee.json に出力しました")


if __name__ == "__main__":
    main()
