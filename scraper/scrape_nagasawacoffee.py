# -*- coding: utf-8 -*-
"""
scrape_nagasawacoffee.py

NAGASAWA COFFEE(nagasawa-coffee.net、岩手県盛岡市上田1丁目11-23、
自家焙煎豆のオンライン販売)の商品情報を取得する。独自EC。

【店舗発見の経緯】
全国再調査(岩手県)で発見(検索結果より)。NYタイムスでも紹介された著名な
自家焙煎ロースターで、1960年代製のドイツ・プロバット社製焙煎機
「UG-15」を使用。単一店舗であることを確認済み(検索結果・公式サイトとも
複数店舗展開の記載なし)。

【対象商品について】
実データ確認済み(sitemap.xml全45件、2026-09時点): ドリップパック
コーヒー単品・ドリップバッグ/コーヒーギフトセット各種・コールドブリュー
バッグ・HERALBONYコラボグッズ(コースター・ボトル)を除いた、コーヒー豆
26銘柄(ストレート20・ブレンド3・デカフェ2、うち同一農園で焙煎度違いの
別商品が4組[エチオピア イルガチェフ ウォッシュドG-1 チェレレクツ、
ブラジル ファゼンダ カルメリート、グアテマラ カルモナ、タンザニア
アカシアヒルズ ケント]含む)を対象とする。

【重量について】
実データ確認済み: 大半の商品は商品名に「100g」「200g」が明記されるが、
一部(タンザニア アカシアヒルズ ケント、ペルー ラ マンダリナ)は重量の
明記が無い。同店の標準的な販売単位は200gが主流(45件中大多数が200g)の
ため、重量未記載の商品は200gと推定する(価格帯も他の200g商品と同水準)。

【商品説明の構造について】
実データ確認済み: `<div class="item_desc_text custom_desc">`内に
「産地/農園/農園主/標高/品種/精選」の各ラベル行(`<br />`区切り)に続いて
自由記述のテイスティング文、末尾に「焙煎度合」+★またはレコードの
段階表示が続く。ラベル行をfarm_noteに、自由記述部分をflavor_notesに
採用し、末尾の焙煎度合表示行は除去する。ブレンド商品はラベル行が無く
自由記述のみ。

【ラベル誤検出の不具合について】
実データ確認済み: 一部商品(タンザニア アカシアヒルズ関連)の自由記述文中に
「農園の環境を更に整える取り組みや...」という「農園」で始まる文が
含まれており、当初のラベル判定パターンが0文字の空白でもマッチしたため
この文をラベル行として誤検出し、正しい農園名を上書きしてしまう不具合が
あった。ラベルキーワードの直後に最低1文字の空白(全角/半角)を必須とする
ことで、地の文がラベル行と誤認識されないよう修正した。また「農園」と
「農園主」の前方一致による誤マッチ(「農園主」が先に「農園」にマッチ
してしまう)を避けるため、alternationの順序を「農園主」→「農園」に変更。
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
    "name": "NAGASAWA COFFEE",
    "url": "https://www.nagasawa-coffee.net/",
    "platform": "独自EC",
    "address": "岩手県盛岡市上田1丁目11-23",
    "prefecture": "岩手県",
    "tel": "019-681-6868",
    "robots_txt_status": "未確認(独自EC構成)",
}

BASE_URL = "https://www.nagasawa-coffee.net"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = [
    "ドリップパック", "ドリップバッグ", "コールドブリュー", "ギフト", "セット",
    "ART", "ボトル", "COASTER",
]

PRICE_PATTERN = re.compile(r'id="pricech">\s*([\d,]+)')
DESC_PATTERN = re.compile(r'<div class="item_desc_text custom_desc">(.*?)</div>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
LABEL_PATTERN = re.compile(r"^(産地|農園主|農園|標高|品種|精選)[　\s]+(.+)$")
ROAST_GAUGE_PATTERN = re.compile(r"[★☆●○]{3,}")


def fetch_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=20)
    return sorted(set(re.findall(r"/product/(\d+)", resp.text)), key=int)


def parse_desc_html(desc_html: str) -> tuple[str | None, dict]:
    lines = [l.strip() for l in re.split(r"<br\s*/?>", desc_html) if l.strip()]
    labels: dict[str, str] = {}
    flavor_lines = []
    for line in lines:
        if ROAST_GAUGE_PATTERN.search(line) or line == "焙煎度合":
            continue
        m = LABEL_PATTERN.match(line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
            continue
        flavor_lines.append(line)
    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return flavor_notes, labels


def build_record(pid: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/product/{pid}", headers=REQUEST_HEADERS, timeout=20)
    html = resp.text
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if not title_m:
        return None
    title = title_m.group(1).strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1).replace(",", "")) if price_m else None
    desc_m = DESC_PATTERN.search(html)
    flavor_notes, labels = parse_desc_html(desc_m.group(1)) if desc_m else (None, {})

    parsed = parse_product(title)
    url = f"{BASE_URL}/product/{pid}"
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

    origin_note = labels.get("産地")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選"):
        parsed["processing_method"] = normalize_processing_method(labels["精選"])

    variety = labels.get("品種")
    farm_parts = [f"{k}: {labels[k]}" for k in ("産地", "農園", "農園主", "標高", "品種", "精選") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else 200
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
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in fetch_ids():
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
    with open("data_nagasawacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nagasawacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
