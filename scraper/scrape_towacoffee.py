# -*- coding: utf-8 -*-
"""
scrape_towacoffee.py

十八珈琲焙煎所(shop.towa-coffee.com、北海道札幌市、自家焙煎豆の
オンライン販売)の商品情報を取得する。BASE(カスタムドメイン)。

【店舗発見の経緯】
全国再調査(北海道)で発見(coffee-labo.co.jp「札幌のおすすめ人気コーヒー豆
専門店10選」)。実店舗(札幌市北円山)は2026-06-05付「閉店のお知らせ」記事に
よると賃貸トラブルにより閉店済みだが、同記事内で新たに専用の焙煎拠点を
整備し、オンライン販売を継続していることを確認済み(閉店=自家焙煎の終了
ではなく、実店舗を持たないオンライン専業への転換)。

【対象商品について】
実データ確認済み(sitemap.xml全18件、2026-09時点): はじめてセット・
こだわりセット(複数銘柄セット)、定期便2種(毎月/2ヶ月に1回、内容が
発送ごとに変わる)、バラエティドリップバッグセット(複数銘柄セット)を
除いた13件(ブレンド3・ストレート10)を対象とする。

【商品説明の構造について】
実データ確認済み: og:descriptionは「テイスティング文+香り/苦味/酸味/
甘み/コクの★評価(除去)+産地エピソード」という構成。ストレート商品は
末尾に《原産国》《生産地域》《標高》《生産者》《品種》《精選》等の
《》区切りラベルが付き、ブレンド商品は末尾が「使用生産国X・Y」という
単純な配合国リストのみ(《》ラベル無し)。★評価行を除いたテキストを
flavor_notesに、《》ラベル(ストレート)または使用生産国リスト(ブレンド)を
farm_noteに採用する。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "十八珈琲焙煎所",
    "url": "https://towa-coffee.com/",
    "platform": "BASE",
    "address": "北海道札幌市",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(BASE標準構成を想定)",
}

BASE_URL = "https://shop.towa-coffee.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["セット", "定期便", "ドリップバック", "ドリップバッグ"]
STAR_RATING_PATTERN = re.compile(r"(香り|苦味|酸味|甘み|コク)[★☆]+")
BRACKET_LABEL_PATTERN = re.compile(r"《([^》]+)》([^《]*)")
BLEND_ORIGIN_PATTERN = re.compile(r"使用生産国\s*(.+)$")

WANTED_LABELS = ("原産国", "生産地域", "標高", "生産者", "品種", "精選")


def fetch_item_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=20)
    return sorted(set(re.findall(r"/items/(\d+)", resp.text)))


def strip_star_ratings(text: str) -> str:
    return STAR_RATING_PATTERN.sub("", text)


def build_record(pid: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{pid}", headers=REQUEST_HEADERS, timeout=20)
    html = resp.text
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if not title_m:
        return None
    title = title_m.group(1).split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', html)
    price = int(float(price_m.group(1))) if price_m else None
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    desc = desc_m.group(1) if desc_m else ""

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{pid}"
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

    is_blend = parsed["category"] == "ブレンド"
    labels: dict[str, str] = {}
    if is_blend:
        m = BLEND_ORIGIN_PATTERN.search(desc)
        flavor_text = desc[: m.start()] if m else desc
        origin_note = None
        farm_note = None
        if m:
            countries = re.split(r"[・\s]+", m.group(1).strip())
            countries = [c for c in countries if c]
            farm_note = f"配合: {'、'.join(countries)}" if countries else None
            origin_note = "、".join(countries)
    else:
        bracket_matches = list(BRACKET_LABEL_PATTERN.finditer(desc))
        flavor_text = desc[: bracket_matches[0].start()] if bracket_matches else desc
        for m in bracket_matches:
            labels[m.group(1).strip()] = m.group(2).strip()
        origin_note = labels.get("原産国")
        parts = [f"{k}: {labels[k]}" for k in WANTED_LABELS if labels.get(k)]
        farm_note = "、".join(parts) if parts else None

    flavor_notes = strip_star_ratings(flavor_text).strip() or None

    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if not is_blend and labels.get("精選"):
        parsed["processing_method"] = normalize_processing_method(labels["精選"])

    variety = labels.get("品種") if not is_blend else None
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
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids = fetch_item_ids()
    records = []
    flavored_records = []
    for pid in pids:
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
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
    with open("data_towacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_towacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
