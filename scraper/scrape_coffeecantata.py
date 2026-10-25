# -*- coding: utf-8 -*-
"""
scrape_coffeecantata.py

コーヒーカンタータ(http://coffeecantatas.com/、神奈川県相模原市中央区矢部3-16-2)の商品情報を取得する。BASE(https://www.coffeecantatas-webshop.net)。

【店舗発見の経緯】
神奈川県の新規発掘調査(2026-10-21)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 200g単位販売の焙煎豆(ブレンド・ストレート・デカフェ)の単品を対象とする。初回限定お試しセットおよび「200g×4袋」の6か月定期購入(豆/粉)は除外(午後のコーヒーは定期購入ページのみのため未収録)。価格は商品の基本価格(豆/粉の選択肢あり)。
商品名・重量・産地・分類は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格(割引表示がある場合は割引後の販売価格)・在庫(item_purchasability)・説明(og:description)・
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
    "name": "コーヒーカンタータ",
    "url": "https://www.coffeecantatas-webshop.net/",
    "platform": "BASE",
    "address": "神奈川県相模原市中央区矢部3-16-2",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://www.coffeecantatas-webshop.net/about および /law (事業者所在地・営業時間11:00-18:00)、http://coffeecantatas.com/ (カフェで生豆を自家焙煎して提供・店頭販売の豆をネット購入できる)、各商品ページを2026-10-20に確認。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.coffeecantatas-webshop.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneならページから判定), 産地(ブレンドはNone))
ITEMS = [   ('9579494', 'カンタータブレンドコーヒー', 200, 'ブレンド', None, None),
    ('9579495', '相模の珈琲 安らぎ', 200, 'ブレンド', '中浅煎り', None),
    ('9579496', '相模の珈琲 憩い', 200, 'ブレンド', None, None),
    ('9579497', '相模の珈琲 和み', 200, 'ブレンド', '深煎り', None),
    ('9579498', 'モーニングブレンド', 200, 'ブレンド', None, None),
    ('9579499', 'ブルマンブレンド', 200, 'ブレンド', None, None),
    ('9580218', 'ブラジル プレミアムショコラ', 200, None, None, 'ブラジル'),
    ('15505156', 'ニカラグア エル・ケツァール', 200, None, None, 'ニカラグア'),
    ('13790578', 'ハワイコナ ハワイアンクイーンコーヒー農園', 200, None, None, 'アメリカ(ハワイ)'),
    ('9579501', 'モカ アールマッカ', 200, None, None, None),
    ('9580212', 'エチオピア カフェインレス', 200, None, None, 'エチオピア'),
    ('9580213', 'コロンビア・エスメラルダ', 200, None, None, 'コロンビア'),
    ('9580214', 'タンザニア AA キリマンジャロ', 200, None, None, 'タンザニア'),
    ('9580216', 'ホンジュラス ハイグロウン', 200, None, None, 'ホンジュラス'),
    ('9580217', 'ブルーマウンテン NO.1', 200, None, None, 'ジャマイカ'),
    ('9580219', 'グアテマラ SHB アゾテア農園', 200, None, None, 'グアテマラ'),
    ('9580221', 'ブラジル サントスNO.2', 200, None, None, 'ブラジル'),
    ('9580223', 'ハワイコナ・EXファンシー', 200, None, None, 'アメリカ(ハワイ)'),
    ('9580224', 'コロンビア ロスカウチョス スプレモ', 200, None, None, 'コロンビア'),
    ('9580225', 'ガヨマウンテン', 200, None, None, 'インドネシア'),
    ('9580226', 'ゴールデンマンデリン', 200, None, None, 'インドネシア'),
    ('9580227', 'メキシコ AL エスパーニャ農園', 200, None, None, 'メキシコ'),
    ('9580228', 'ケニア マサイAA', 200, None, '深煎り', 'ケニア')]

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
    if "ハイグロウン" in name:  # 「ハイグロウン」(高地産の等級)を焙煎度の「ハイ」と誤判定しない
        parsed["roast_level"] = None
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
    with open("data_coffeecantata.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeecantata.json に出力しました")


if __name__ == "__main__":
    main()
