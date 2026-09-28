# -*- coding: utf-8 -*-
"""
scrape_dayandcoffee.py

Day & Coffee(dayandcoffee.official.ec、山形県山形市香澄町1丁目11-18
とみひろビル01、運営:株式会社デイアンド、自家焙煎スペシャルティコーヒー
ブランド)の商品情報を取得する。BASE(official.ecドメイン)。

【店舗発見の経緯】
全国再調査(山形県)でWeb検索から発見(山形駅前本店・本町七日町店の2拠点、
チェーンには該当しない)。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆」カテゴリ(ID:4811300)全23件
のうち、定期便2種・ギフトボックス・テイスティングセット2種を除いた、
コーヒー豆単品9銘柄(各100g/200gの2サイズ展開、コロンビア LA CUMBRE
GEISHAのみ70g/100g)を対象とする。各銘柄の最小サイズを代表として採用。
「ブラジル PASSEIO」と「ブラジル PASSEIO NATURAL」は精選方法違いの別銘柄
(実データ確認済み、商品名・商品ページとも別)。

【商品説明の構造について】
実データ確認済み: `<meta property="og:description">`に「【商品説明】
ORIGIN：...ROAST：...TASTE：...COMMENT :...(自由記述)...生産国：...
生産エリア：...(農園：...)精製方法：...標高：...品種：...焙煎所：Day &
Coffee【製造者情報】...」という形式で、英語ラベル(ORIGIN/ROAST/TASTE/
COMMENT)と日本語ラベル(生産国/生産エリア/生産者/農園/精製方法/標高/品種)が
1つの文字列に連結されている。既知ラベル群をまとめて1回のsplitで処理する
ことで、自由記述(COMMENT)の後にラベルが続く場合の境界を自動的に切り出す。
ただし「生産者たちのモチベーションも高まり」のようにCOMMENT本文中に偶然
「生産者」という文字列が地の文として登場するケースがあるため、コロン直後
必須の正規表現(ラベル+コロン)で誤マッチを防いでいる。「焙煎所：Day &
Coffee」は全銘柄共通の無意味な情報のため、この文字列以降を先に切り落として
から抽出する。

【在庫状態について】
実データ確認済み: iskoffee.com・culminoと同じBASE系列のため、GA計測用
インラインJSのitem_purchasability("purchasable"/"unpurchasable")フィールド
で判定する。
"""

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
    "name": "Day & Coffee",
    "url": "https://dayandcoffee.official.ec/",
    "platform": "BASE(official.ec)",
    "address": "山形県山形市香澄町1丁目11-18 とみひろビル01",
    "prefecture": "山形県",
    "tel": "023-606-0445",
    "robots_txt_status": "未確認(BASE標準構成、iskoffee.com/culminoと同系列プラットフォーム)",
}

BASE_URL = "https://dayandcoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "131080335",  # 【中浅煎り】エチオピア CHELBESA 100g
    "134376566",  # 【深煎り】ペルー LA CAPILLA 100g (SOLD OUT)
    "135687061",  # 【浅煎り】コロンビア LA CUMBRE GEISHA 70g
    "139024371",  # 【浅煎り】ルワンダ SIMBI 100g
    "150937515",  # 【中煎り】ブラジル PASSEIO NATURAL 100g
    "150943029",  # 【深煎り】グアテマラ FRAIJANES 100g
    "155760416",  # 【浅煎り】エチオピア ANASORA 100g
    "80078450",   # 【デカフェ】メキシコ CHIAPAS DECAF 100g
    "97029937",   # 【中煎り】ブラジル PASSEIO 100g
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*Day")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

LABEL_MAP = {
    "ORIGIN": "ORIGIN", "ROAST": "ROAST", "TASTE": "TASTE", "COMMENT": "COMMENT",
    "生産国": "生産国", "生産エリア": "生産エリア", "生産者": "生産者",
    "農園": "農園", "精製方法": "精選方法", "標高": "標高", "品種": "品種",
}
LABEL_PATTERN = re.compile("(" + "|".join(re.escape(k) for k in LABEL_MAP) + r")\s*[:：]\s*")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = title_m.group(1).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1) if desc_m else ""
    desc = desc.split("焙煎所")[0].split("【製造者情報】")[0]

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        key = LABEL_MAP[raw_label]
        labels.setdefault(key, value.strip())

    region = labels.get("生産国")
    detected = (region and detect_country_name(region)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if region else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    is_decaf = "デカフェ" in title or "DECAF" in title.upper()
    decaf_process = labels.get("精選方法") if is_decaf else None

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産エリア", "生産者", "農園", "標高", "品種") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

    flavor_parts = [f"{k}: {labels[k]}" for k in ("TASTE", "COMMENT") if labels.get(k)]
    if flavor_parts:
        flavor_notes = "\n".join(flavor_parts)
    else:
        # 実データ確認済み: 一部の旧型商品ページ(構造化ラベル無し)は自由記述の
        # 1段落のみで構成される。ラベルが1つもマッチしなかった場合はその全文を使う。
        flavor_notes = desc.strip() or None
    roast_hint = labels.get("ROAST")

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
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "decaf_process": decaf_process,
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
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_dayandcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dayandcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
