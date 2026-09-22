# -*- coding: utf-8 -*-
"""
scrape_onibuscoffee.py

ONIBUS COFFEE(onibuscoffee-jp.com、ABOUT LIFE COFFEE BREWERS等を含め国内
7拠点、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json全件取得方式)。

【店舗発見の経緯】
高田馬場エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、渋谷
エリアを調査した際に「ABOUT LIFE COFFEE BREWERS」(渋谷区道玄坂)がONIBUS
COFFEE運営のブランドの一つと判明して発見。2012年に世田谷区奥沢で創業したが、
公式サイトの店舗一覧(onibuscoffee.com/pages/locations、2026-09確認)には
奥沢店が無く、現在は中目黒駅前店・中目黒三丁目店・八雲店・自由が丘店・
那須店(以上ONIBUS COFFEE)、道玄坂店・渋谷一丁目店(以上ABOUT LIFE COFFEE
BREWERS)の国内7店舗+海外3店舗(台北・バンコク2・台中・ホーチミン)を
展開している。オンラインストアは1つに統合されているため本スクレイパーは
店舗名を「ONIBUS COFFEE」として一括りで扱う(7店舗という規模は「11店舗
以上のチェーンは対象外」の基準には該当しない)。SHOP_INFOの住所は現存する
旗艦店である中目黒駅前店を代表値として採用する。

【対象商品について】
実データ確認済み(全20件): product_type=="コーヒー豆"のうち、「コールド
ブリューパック」(個包装の水出しパック)・「【送料無料】シングルオリジン
定期便」(特定銘柄を指さない定期便)・「テイスティングセット （ブレンド /
シングルオリジン）」(複数銘柄セット)・「ドリップバッグ（10個入り）」・
「ドリップバッグ -ギフトボックス-（6個入り）」の5件が非対象。残る15件
(ストレート11・デカフェ1・ブレンド3)が対象。

【body_htmlの構造について】
実データ確認済み(全対象商品で共通): 最初の<p>がテイスティング文、続けて
「----------」の区切り線、その後「生産地：/農園：/生産者：/品種：/
精製方法：/標高：/テイスティングコメント：」のラベル付き仕様が並ぶ
(一部の項目が欠けている商品もある)。区切り線より前のテイスティング文の
みをflavor_notesとして採用し、ラベル行から生産地(origin_country推定用)・
品種・精製方法を個別に抽出する。装飾用の多重ネストされた<span
style="vertical-align: inherit;">タグはget_text()で自然に無視される。

【在庫状態について】
実データ確認済み: Shopifyのtags配列に「label-終売-gray」(終売)・
「label-残りわずか-gray」(在庫僅少、購入は可能)等のラベルタグが付与されて
いる。「終売」タグがある商品のみstock_status="終売"として扱い、
「残りわずか」は販売中のまま扱う(購入不可ではないため)。

【重量・挽き方について】
実データ確認済み: 全商品が「100g/200g/500g/1kg」×「豆のまま/中挽き/
粗挽き/細挽き」のバリアント構成で、重量ごとに価格が変わる(挽き方による
価格差は無い)。最小重量かつ「豆のまま」のバリアントを代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "ONIBUS COFFEE",
    "url": "https://onibuscoffee.com/",
    "platform": "Shopify(サイト全体のproducts.jsonエンドポイントを利用。"
                "ABOUT LIFE COFFEE BREWERSを含む国内7拠点で共通運用)",
    "address": "東京都目黒区上目黒2-14-1",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(Shopify標準テンプレートを想定)",
}

BASE_URL = "https://onibuscoffee-jp.com"
PRODUCTS_JSON_URL = f"{BASE_URL}/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー豆"
NON_BEAN_KEYWORDS = ["コールドブリュー", "定期便", "テイスティングセット", "ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]|(\d+)\s*kg", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"^(生産地|農園|生産者|品種|精製方法|標高|組合|ウォッシングステーション|テイスティングコメント|コーヒー豆)\s*[：:]\s*(.+)$")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_weight_g(text: str) -> int | None:
    m = re.search(r"(\d+)\s*kg", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", text)
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    whole_bean = [v for v in variants if "豆のまま" in (v.get("title") or "")]
    pool = whole_bean or variants
    if not pool:
        return None
    return min(pool, key=lambda v: parse_weight_g(v.get("title") or "") or float("inf"))


def parse_body(body_html: str) -> tuple[str | None, dict]:
    """理由はモジュールdocstring参照。基本形は「テイスティング文→区切り線
    （----------）→ラベル付き仕様」の順だが、デカフェ商品1件のみ「ラベル付き
    仕様→テイスティングコメント→説明文」という逆順の構成だった(実データ
    確認済み)。順序に依存せず、行ごとにラベル行(「ラベル：値」)かどうかを
    判定し、ラベル行はlabelsに、それ以外の行(区切り線含む空行除去後)は
    出現順のままflavor_notesとして連結する方式に統一した。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text("\n", strip=True)

    labels = {}
    flavor_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or set(line) == {"-"}:
            continue
        m = LABEL_PATTERN.match(line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
        else:
            flavor_lines.append(line)

    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return flavor_notes, labels


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"{BASE_URL}/products/{product.get('handle')}"

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])) if variant else None,
            "product_url": product_url,
        }

    flavor_notes, labels = parse_body(product.get("body_html") or "")

    origin_note = labels.get("生産地")
    if origin_note:
        detected = detect_country_name(origin_note) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精製方法")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種")
    farm_note = labels.get("農園") or labels.get("生産者")

    variant = pick_canonical_variant(product.get("variants", []))
    price = int(float(variant["price"])) if variant else None
    weight_g = parse_weight_g((variant or {}).get("title") or "")

    tags = product.get("tags") or []
    if "label-終売-gray" in tags:
        stock_status = "終売"
    else:
        stock_status = "販売中"

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
        "variety": variety,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    target_products = [p for p in products if p.get("product_type") == TARGET_PRODUCT_TYPE]

    records = []
    flavored_records = []
    for product in target_products:
        record = build_record(product)
        if record is None:
            continue
        if record.get("is_flavored"):
            flavored_records.append(record)
        else:
            records.append(record)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_onibuscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_onibuscoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
