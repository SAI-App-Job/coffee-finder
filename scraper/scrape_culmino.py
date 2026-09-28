# -*- coding: utf-8 -*-
"""
scrape_culmino.py

CoffeeRoaster&Cafe culmino(クルミーノ、cafeculmino.thebase.in、山形県
寒河江市寒河江字内ノ袋32、店内で自家焙煎するローステリア)の商品情報を
取得する。BASE(thebase.inサブドメイン)。

【店舗発見の経緯】
全国再調査(山形県)でmamenavi.info「山形の自家焙煎珈琲店ガイド」から発見。
ふるさと納税返礼品にも採用。

【対象商品について】
実データ確認済み(2026-09時点): トップページ全17商品のうち、100gの
コーヒー豆単品8件(SOLD OUT中の1件を含む)のみを対象とする。3種セット・
ドリップバッグ各種セット・クルミーノブレンド400g(100g版と重複)・
寒河江珈琲ブレンドカフェラテベース(液体濃縮タイプでコーヒー豆でない)・
各種詰め合わせギフトは対象外。

【商品詳細データの取得元について】
実データ確認済み: `<meta property="og:description">`に商品説明の全文が
入っており、単一農園商品には英語ラベル(Flaver･Taste/Producer/Variety/
Process/Altitude/Roast)、一部商品(カフェインレスのコロンビア)には日本語
ラベル(生産者/品種/生産処理/標高/ロースト)が使われる。両方の表記に
対応する。ブレンド商品(クルミーノブレンド)は「ブレンド使用銘柄」として
配合豆と焙煎度の箇条書きがある。

【在庫状態について】
実データ確認済み: iskoffee.comと同じBASEプラットフォームのため、GA計測用
インラインJSに埋め込まれたitem_purchasability("purchasable"/
"unpurchasable")フィールドで在庫を判定する(HTML中に常駐するJSテンプレートの
"SOLD OUT"文字列は在庫状態を問わず常に存在するため使えない)。
"""

import html
import json
import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "CoffeeRoaster&Cafe culmino",
    "url": "https://cafeculmino.thebase.in/",
    "platform": "BASE(thebase.in)",
    "address": "山形県寒河江市寒河江字内ノ袋32",
    "prefecture": "山形県",
    "robots_txt_status": "未確認(BASE標準構成、iskoffee.comと同系列プラットフォーム)",
}

BASE_URL = "https://cafeculmino.thebase.in"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "145054697",  # エチオピア アリーチャ レラ (SOLD OUT)
    "155567567",  # エチオピア ニグセゲメダ シリンガ
    "147810032",  # ブルンジ カランボ
    "157244484",  # グァテマラ パスクアル・モラレス
    "157228053",  # タンザニア ヘズヤ
    "155571106",  # インドネシア プトラ ガヨ
    "70499811",   # カフェインレス コロンビア サン アグスチン
    "25290083",   # クルミーノブレンド 100g
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*CoffeeRoaster")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')

LABEL_MAP = {
    "Producer": "生産者", "生産者": "生産者",
    "Variety": "品種", "品種": "品種",
    "Process": "精選方法", "生産処理": "精選方法",
    "Altitude": "標高", "標高": "標高",
    "Roast": "ロースト", "ロースト": "ロースト",
}
LABEL_PATTERN = re.compile(
    "(" + "|".join(re.escape(k) for k in LABEL_MAP) + r")\s*[:：]\s*"
)


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = html.unescape(desc_m.group(1)) if desc_m else ""
    # 送料についての定型文以降はラベル抽出・地の文のどちらにも不要なため事前に切り落とす
    desc = desc.split("◆送料について")[0]

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    parsed = parse_product(title)
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

    parts = LABEL_PATTERN.split(desc)
    labels = {}
    for raw_label, value in zip(parts[1::2], parts[2::2]):
        # 最後にマッチしたラベルの値には、後続する自由記述の地の文が丸ごと
        # 連結されてしまう(次のラベルが無いため区切りが無い)。標高・ロースト
        # は特に頻出する最終ラベルのため、値の形式そのもの(数値+m / 既知の
        # ロースト語+任意の日本語カッコ)で個別に境界を切り直す。
        key = LABEL_MAP[raw_label]
        labels.setdefault(key, value.strip())
    if "標高" in labels:
        m = re.match(r"^[\d,.\s\-~〜－]+[mM]", labels["標高"])
        if m:
            labels["標高"] = m.group(0).strip()
    if "ロースト" in labels:
        m = re.match(r"^(Light|Medium-Light|Medium-Dark|Medium|Dark)(?:\s*（[^）]*）)?", labels["ロースト"])
        labels["ロースト"] = m.group(0).strip() if m else None
        if not labels["ロースト"]:
            del labels["ロースト"]

    intro = parts[0].strip()

    detected = detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産者", "品種", "標高") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None
    roast_hint = labels.get("ロースト")

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
        "roast_hint": roast_hint,
        "flavor_notes": intro or None,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
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
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_culmino.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_culmino.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
