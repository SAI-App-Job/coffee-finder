# -*- coding: utf-8 -*-
"""
scrape_chaca.py

茶果(Chaca、coffee-chaca.com、福岡市早良区西新5丁目14-44、注文後に
特注の高速焙煎機で2~5分焙煎する自家焙煎豆専門店)の商品情報を取得する。

【住所・自家焙煎について】
公式サイトの「お店紹介」ページ(https://coffee-chaca.com/category1/)に
「福岡市早良区西新５丁目14-44」の住所と「茶果の珈琲豆は生豆よりすべて
自家焙煎」との記載を確認済み(2026-09時点)。

【プラットフォームについて】
サイト自体はJimdo製の静的サイトで、購入機能のみ外部カートサービス
cart.ec-sites.jp(shop_id=5027)に委譲する構成(珈琲の富田屋
scrape_tomitaya.pyと同じ「たまごリピート」系だが、あちらは自店ページに
価格が直接書かれているのに対し、本サイトは価格自体もカート側の
JSウィジェット(js2.ec-sites.jp/syncro.js → syncro.php)で動的に注入される
点が異なる。syncro.jsのソースを解析した結果、実際の価格・在庫データは
`https://js2.ec-sites.jp/syncro.php?sh=<shop_id>&it=<es_item_id>`への
GETリクエストで(Shift-JISエンコードのHTML/JS混在レスポンスとして)取得
できることを確認済みのため、この直接呼び出し方式を採用する。

【商品一覧の取得方法について】
実データ確認済み: サイト自身のsitemap.htmlから「珈琲豆ご購入」
(category18)配下の商品記事(category19~22, category4, category7,
category8の各サブカテゴリのentryNN.html)、全40件を対象とする
(ドリップバッグ・ギフト・器具は`category18`の外側の別ナビ項目のため
含まれない)。

【商品詳細ページの構造化データについて】
実データ確認済み: 各記事ページ本文に「生産地」「農園名」「農園主」
「品種」「精製」をラベル:値の表形式で持つ(ブレンドは非公開のため
欄自体が無い)。商品名(h1.headerimg-title)から
coffee_parser.parse_product()でも産地判定できるが、より正確な
生産地表記(「ニカラグア共和国／ヒノテガ県」等)を優先して使う。

【重量・注文形態について】
実データ確認済み: 全銘柄が「焙煎前200g（生豆）」を基準単位として
販売しており(焙煎後は数割減、farmNote相当の記述として保持)、
一覧上の重量違いバリエーションは無い。weight_g=200固定とする。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method, detect_country_name

SHOP_INFO = {
    "name": "茶果",
    "url": "https://coffee-chaca.com/",
    "platform": "Jimdo + 外部カート連携(cart.ec-sites.jp)",
    "address": "福岡県福岡市早良区西新5丁目14-44",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認(2026-09時点。Jimdo標準サイトのため個別のrobots.txt制限は"
                          "見つからず、低頻度アクセスのみ行う)",
}

BASE_URL = "https://coffee-chaca.com"
SHOP_ID = "5027"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
UNIT_WEIGHT_G = 200  # 理由はモジュールdocstring参照
# 実データ確認済み: category18配下でも「珈琲ギフト」(category22)・
# 「ギフト用パッケージ」(category21の一部、詰め合わせ用の空箱)は
# コーヒー豆単品ではないため除外する
NON_BEAN_KEYWORDS = ["珈琲ギフト", "入れ用箱"]

ENTRY_PATHS = [
    "category19/entry16", "category19/entry17", "category19/entry21", "category19/entry54",
    "category19/entry56", "category19/entry61", "category19/entry64",
    "category20/entry18", "category20/entry19", "category20/entry27", "category20/entry28",
    "category20/entry39", "category20/entry49", "category20/entry50", "category20/entry51",
    "category20/entry52", "category20/entry53",
    "category21/entry33", "category21/entry34", "category21/entry35", "category21/entry36",
    "category21/entry37", "category21/entry38",
    "category22/entry30", "category22/entry31", "category22/entry32",
    "category4/entry5", "category4/entry6", "category4/entry8", "category4/entry9",
    "category4/entry10", "category4/entry11", "category4/entry12", "category4/entry13",
    "category7/entry45", "category7/entry46", "category7/entry47", "category7/entry48",
    "category8/entry41", "category8/entry43",
]

ITEM_ID_PATTERN = re.compile(r"es_item_id\s*=\s*(\d+)")
LABEL_PATTERN = re.compile(r"(生産地|農園名|農園主|品種|精製)\s*\n\s*([^\n]+)")
PRICE_PATTERN = re.compile(r"cost_\w+\s*=\s*(\d+)")
SOLDOUT_PATTERN = re.compile(r"在庫切れです")


def fetch_entry(path: str) -> str:
    resp = requests.get(f"{BASE_URL}/category18/{path}.html", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def extract_title(html: str) -> str:
    m = re.search(r'<h1 class="headerimg-title">([^<]+)</h1>', html)
    return m.group(1).strip() if m else ""


def extract_fields(html: str) -> dict:
    # <br>をタブ的な区切りとして扱うため改行に正規化してからラベル行を拾う
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    fields = {}
    for label, value in LABEL_PATTERN.findall(text):
        fields[label] = value.strip()
    return fields


def fetch_price_and_stock(item_id: str) -> tuple[int | None, bool]:
    resp = requests.get(
        "https://js2.ec-sites.jp/syncro.php",
        params={"sh": SHOP_ID, "it": item_id},
        headers=REQUEST_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    text = resp.content.decode("shift_jis", errors="replace")
    price_m = PRICE_PATTERN.search(text)
    price = int(price_m.group(1)) if price_m else None
    out_of_stock = bool(SOLDOUT_PATTERN.search(text))
    return price, out_of_stock


def build_record(path: str, html: str) -> dict | None:
    title = extract_title(html)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    item_id_m = ITEM_ID_PATTERN.search(html)
    if not item_id_m:
        print(f"[warn] es_item_idが見つかりません: {path}")
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": f"{BASE_URL}/category18/{path}.html",
        }

    fields = extract_fields(html)
    if fields.get("生産地"):
        country = detect_country_name(fields["生産地"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    if fields.get("精製"):
        parsed["processing_method"] = normalize_processing_method(fields["精製"])

    farm_note_parts = []
    if fields.get("農園名"):
        farm_note_parts.append(f"農園名: {fields['農園名']}")
    if fields.get("農園主"):
        farm_note_parts.append(f"農園主: {fields['農園主']}")
    if fields.get("品種"):
        farm_note_parts.append(f"品種: {fields['品種']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    price, structural_out_of_stock = fetch_price_and_stock(item_id_m.group(1))
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "farm_note": farm_note,
        "blend_components": [],
        "price": price,
        "weight_g": UNIT_WEIGHT_G,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/category18/{path}.html",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for path in ENTRY_PATHS:
        try:
            html = fetch_entry(path)
            detail = build_record(path, html)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {path} ({e})")
            continue

        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_chaca.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chaca.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
