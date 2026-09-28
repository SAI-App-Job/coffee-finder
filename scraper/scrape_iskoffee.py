# -*- coding: utf-8 -*-
"""
scrape_iskoffee.py

IsKoffee(イズコーヒー、iskoffee.com→iskoffee.buyshop.jp、山形県山形市南館
3丁目5-19、コーヒー農園への買付渡航を自ら行うローステリア)の商品情報を
取得する。BASE(buyshop.jpドメイン)。

【店舗発見の経緯】
全国再調査(山形県)でcoffee-labo.co.jp記事から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「IS BEANS」カテゴリ(カテゴリID3188943)に
掲載された7件全て(単一農園4件+ブレンド3件)を対象とする。DRIP BAG・
IS DELIVERY(定期便)・水出しアイスコーヒー・コーヒー牛乳の素は対象外。

【商品詳細データの取得元について】
実データ確認済み: 商品詳細ページ本文よりも`<meta property="og:description">`
の方が、改行等の装飾を除いた同一テキストを安定して取得できるため、こちらを
情報源として使う。単一農園商品には「For Beans」セクションに生産者・農園名・
生産国・品種・標高・収穫・精製処理の構造化ラベルがあり、ブレンド商品には
「Blend Concept」の自由記述のみで構造化ラベルは無い。

【文字正規化について】
実データ確認済み: サイトの表記は全角数字・全角スペース・全角コロンが
商品によって不統一(例:「収穫　２０２４年」と「収穫 2025年」が混在)。
unicodedata.normalize("NFKC", ...)で全角英数字・全角スペース・全角コロンを
半角に統一してから正規表現抽出を行う。

【robots.txtについて】
実データ確認済み(2026-09): buyshop.jpのrobots.txtは"python-requests"
"curl"等のデフォルトUser-Agent文字列を名指しでDisallowしているが、
"User-Agent: *"では商品ページ・カテゴリページを含め明示的にAllowしている。
本スクレイパーは連絡先を含むカスタムUser-Agentを使用し、それらの既定UA名とは
一致しないため"*"のAllow規則の対象となる。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "イズコーヒー",
    "url": "https://iskoffee.com/",
    "platform": "BASE(buyshop.jp)",
    "address": "山形県山形市南館3丁目5-19",
    "prefecture": "山形県",
    "robots_txt_status": "実質許可(2026-09確認。User-Agent: *では商品ページ・カテゴリページを含めAllow: /。"
                          "\"python-requests\"\"curl\"等の既定UA文字列のみ個別にDisallowしているが、"
                          "本スクレイパーは連絡先入りのカスタムUAを使うため該当しない)",
}

BASE_URL = "https://iskoffee.buyshop.jp"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "121374394",  # 【NEW】エルポルベニール農園
    "118066111",  # 【夏季限定】サンセットブレンド2026
    "62085214",   # カサブランカ農園パカマラ・N
    "121374405",  # 【NEW】エンバシー農園
    "55622805",   # 山形ブレンド
    "45303362",   # エスプレッソローストブレンド
    "144596347",  # 【5・6月限定】ワイルドプランツブレンド
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*Iskoffee")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
WEIGHT_PATTERN = re.compile(r"内容量[：:]\s*(\d+)\s*(?:g|グラム|㌘)")
# 実データ確認済み: ページ内には全商品共通のJSテンプレート文字列として
# "SOLD OUT"が常に埋め込まれており(表示可否はJS実行時に切り替わる)、
# HTML直接取得では常にマッチしてしまうため在庫判定には使えない。
# 実際の在庫状態はGA計測用インラインJSに埋め込まれた
# item_purchasability("purchasable"/"unpurchasable")フィールドで判定する。
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
FORBEANS_LABELS = ["生産者", "農園名", "生産国", "品種", "標高", "収穫", "精製処理"]
LABEL_SPLIT_PATTERN = re.compile("(" + "|".join(FORBEANS_LABELS) + r")\s*")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html = resp.text

    title_m = TITLE_PATTERN.search(html)
    if not title_m:
        return None
    title = re.sub(r"\s*豆/粉選択可\s*$", "", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html)
    desc = unicodedata.normalize("NFKC", desc_m.group(1)) if desc_m else ""

    weight_m = WEIGHT_PATTERN.search(desc)
    weight_g = int(weight_m.group(1)) if weight_m else None

    main_text = desc.split("■内容量")[0].strip()

    parsed = parse_product(title)
    price_m = re.search(r'"price":\s*"?(\d+)', html) or re.search(r'product:price:amount" content="(\d+)"', html)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    url = f"{BASE_URL}/items/{item_id}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    farm_note = None
    flavor_notes = main_text
    if "For Beans" in main_text:
        pre, forbeans_chunk = main_text.split("For Beans", 1)
        flavor_notes = pre.strip() or None
        parts = LABEL_SPLIT_PATTERN.split(forbeans_chunk)
        labels = {}
        for label, value in zip(parts[1::2], parts[2::2]):
            labels[label] = value.strip()

        country = labels.get("生産国")
        detected = (country and detect_country_name(country)) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if country else "raw_name"

        farm_parts = [f"{k}: {labels[k]}" for k in ("農園名", "標高", "品種", "収穫") if labels.get(k)]
        farm_note = "、".join(farm_parts) if farm_parts else None
    else:
        parsed = apply_category_hint_fallback(parsed, title)

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
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
        time.sleep(1)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_iskoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iskoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
