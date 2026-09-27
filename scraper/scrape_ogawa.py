# -*- coding: utf-8 -*-
"""
scrape_ogawa.py

小川珈琲本店(oc-shop.co.jp、京都府京都市右京区西京極北庄境町75、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査で判明した「11店舗以上のチェーン」基準の境界線
ケース。直営9店舗(スーパー等への卸売りは店舗数に含まれない)のため
「11店舗以上」の基準には該当しないと判断し実装対象とした(ユーザーの
指示によりチェーン店の定義に沿って店舗数ベースで判定)。

【対象商品について】
実データ確認済み(/products.json、product_type="レギュラーコーヒー"の
92件、2026-09時点): 同一銘柄が「豆/粉」の挽き方違い・「まとめ買い」の
個数違い(×5個/×12個/×25個等)で大量に重複展開されている(実質的な
ユニーク銘柄数は24件程度)。水出し・アイスコーヒー(液体/粉末パック)・
福袋・お試しセット・サブスクリプション・カフェインレスコーヒーセット
(複数銘柄セット)は対象外。重複を除いた24銘柄(ブレンド14・ストレート6・
期間限定ブレンド4)の代表ハンドルを直接指定して取得する(全92件を走査
すると重複判定のロジックが複雑になるため、代表ハンドルを事前に選定した)。

【商品説明の構造について】
実データ確認済み: body_htmlは「味わいコメントの見出し+テイスティング文+
香り/苦味/酸味/コクの◆記号評価(除去)+(一部商品のみ)生豆生産国/地域/
生産者/標高/品種/精選のラベル+まとめ買い訴求のクロスセルリンク(除去)」
という構成だが、高価格帯のマイクロロット商品は農園ストーリー中心の
自由記述でラベルを持たない場合がある。img/iframeタグは除去し、
「まとめ買いがお得」以降を除去したうえでラベル抽出・残りをflavor_notes
として採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "小川珈琲本店",
    "url": "https://www.oc-ogawa.co.jp/",
    "platform": "Shopify",
    "address": "京都府京都市右京区西京極北庄境町75",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://oc-shop.co.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_HANDLES = [
    "r-orgoriginal-b", "r-ocpremium-b", "r-bluemountain-b", "r-coffeeshop-b", "r-orgguatemala-b",
    "r-caffeineless-p", "r-fairtrademoca-b", "r-kilimanjaro-p", "r-orgcaffeinelessmoca-p",
    "rcp-blend3", "rcp-blend3moca", "rcp-kaori", "rcp-kaoriorganic", "960", "929",
    "rcb-panama-don-pepe-jw", "957", "932", "940", "lab_100047", "lab_100015",
    "rcp-akicoffee", "rcp-natucoffee", "rcp-harucoffee", "rcp-fuyucoffee",
]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"(生豆生産国|地域|生産者|標高|品種|精選|精製)\s*[：:]\s*([^\n]*)")


def fetch_product(handle: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/products/{handle}.json", headers=REQUEST_HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    return resp.json().get("product")


def parse_body(body_html: str) -> tuple[str | None, dict]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    for tag in soup.find_all(["img", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.split(r"まとめ買いがお得|【まとめ買い", text)[0]

    labels = {m.group(1): m.group(2).strip() for m in LABEL_PATTERN.finditer(text)}
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or "◆" in line:
            continue
        if line in ("味わいコメント", "【味わいコメント】"):
            continue
        if LABEL_PATTERN.match(line):
            continue
        lines.append(line)
    flavor_notes = "\n".join(lines) if lines else None
    return flavor_notes, labels


def pick_variant(variants: list[dict]) -> dict | None:
    whole_bean = [v for v in variants if "豆" in (v.get("title") or "") and "粉" not in (v.get("title") or "")]
    pool = whole_bean or variants
    return pool[0] if pool else None


def build_record(handle: str) -> dict | None:
    product = fetch_product(handle)
    if not product:
        return None
    title = product["title"].strip()
    variant = pick_variant(product.get("variants") or [])
    if not variant:
        return None
    price = int(float(variant["price"]))

    parsed = parse_product(title)
    url = f"{BASE_URL}/products/{handle}"
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

    flavor_notes, labels = parse_body(product.get("body_html"))

    origin_note = labels.get("生豆生産国")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精選") or labels.get("精製")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種")
    farm_parts = [p for p in [labels.get("地域"), labels.get("生産者"), labels.get("標高")] if p]
    farm_note = "、".join(farm_parts) if farm_parts else None

    weight_m = WEIGHT_PATTERN.search(title)
    stock_status = detect_stock_status(title)

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
        "blend_components": [],
        "price": price,
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for handle in TARGET_HANDLES:
        try:
            detail = build_record(handle)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {handle} ({e})")
            continue
        if detail is None:
            print(f"[warn] 商品が見つかりません: {handle}")
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_ogawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ogawa.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
