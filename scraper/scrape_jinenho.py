# -*- coding: utf-8 -*-
"""
scrape_jinenho.py

焙煎珈琲 自然芳(jinenho.com、山形県山形市成沢西1丁目5-34、自家焙煎豆の
店頭販売専門店)の商品情報を取得する。独自静的サイト(商品詳細は個別URL
/beans/<slug>/、在庫・価格情報はJSON API /data/beans-status.jsonで
動的に上書きされる)。

【店舗発見の経緯】
全国再調査(山形県)でmamenavi.info「山形の自家焙煎珈琲店ガイド」から発見。

【対象商品について】
実データ確認済み(2026-09時点): トップページの週替わりセール枠に表示される
「weekly-bean-catalog」の11件に加え、直接リンクは無いが個別ページが存在する
「genuine-kilimanjaro-peaberry」(完売)を含め、計12件の商品ページ
(/beans/<slug>/)を対象とする。全商品ページに生産国・エリア・農園/生産者・
標高・品種・精製方法・焙煎度の構造化データ(dl.bean-facts)があり、これを
farm_noteの構成要素として使う(生産国はorigin_countryへ、精製方法は
processing_methodへ、焙煎度は8段階の標準ロースト語彙(ライト〜イタリアン)
ではなく「中煎り（やや深め）」のような表記のためroast_hintへ、それぞれ
別フィールドとして格納)。

【重量について】
価格の基準表記は全商品で「生豆200gを焙煎」であり、これは焙煎前の生豆重量を
指す可能性が高く、焙煎後の実際の商品重量(通常は生豆から15〜20%程度目減り)
とは異なる可能性がある。サイト上に焙煎後の正確な重量表記が無いため、
weight_gは確定情報ではないとしてnullとし、unit_noteに原文の基準表記を
そのまま記録する。

【在庫状態について】
実データ確認済み: オンライン決済カートは無く、電話注文のみ(「ご注文・在庫の
確認は、お電話でお問い合わせください」との明記あり)。/data/beans-status.json
のavailableフラグ(true/false)とstatusLabel("完売"/"販売中"等)で在庫状態を
判定する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎珈琲 自然芳",
    "url": "https://jinenho.com/",
    "platform": "独自静的サイト(オンライン決済カート無し、電話注文制)",
    "address": "山形県山形市成沢西1丁目5-34",
    "prefecture": "山形県",
    "tel": "023-688-8662",
    "robots_txt_status": "未確認(独自サイト構成)",
}

BASE_URL = "https://jinenho.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

SLUGS = [
    "kenya-red-mountain", "brazil-aroma-chocolat", "mandheling-tobako",
    "panama-coffee", "guatemala-coffee", "colombia-coffee", "tanzania-coffee",
    "ethiopia-nansebo", "blend-jinen", "san-jose-javanica-washed",
    "guatemala-antigua-peaberry", "genuine-kilimanjaro-peaberry",
]

FACT_PATTERN = re.compile(r"<dt>([^<]+)</dt><dd>([^<]*)</dd>")
DESC_PATTERN = re.compile(
    r'<section class="bean-description"[^>]*>.*?<div class="bean-description__section">\s*<p>(.*?)</p>',
    re.DOTALL,
)


def build_record(slug: str, status: dict) -> dict | None:
    resp = requests.get(f"{BASE_URL}/beans/{slug}/", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html = resp.text

    title_m = re.search(r"<h1>([^<]+)</h1>", html)
    if not title_m:
        return None
    title = title_m.group(1).strip()

    facts = dict(FACT_PATTERN.findall(html))
    desc_m = DESC_PATTERN.search(html)
    flavor_notes = desc_m.group(1).strip() if desc_m else None

    parsed = parse_product(title)
    info = status.get(slug, {})
    price = info.get("price")
    available = info.get("available", True)
    raw_status_label = info.get("statusLabel")
    # san-jose-javanica-washedで実データ確認済み: available=falseなのに
    # statusLabel="販売中"のまま(サイト側の更新漏れ)という矛盾したケースがある。
    # available(在庫の有無を示す一次フラグ)を正としてstock_statusを組み立てる。
    status_label = raw_status_label if (raw_status_label and raw_status_label != "販売中") else (
        "販売中" if available else "完売"
    )

    url = f"{BASE_URL}/beans/{slug}/"
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

    country = facts.get("生産国")
    detected = (country and detect_country_name(country)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if country else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing = facts.get("精製方法")
    if processing:
        from coffee_parser import normalize_processing_method
        parsed["processing_method"] = normalize_processing_method(processing) or parsed["processing_method"]

    farm_parts = []
    for key in ("エリア", "農園 / 生産者", "標高", "品種"):
        if facts.get(key):
            farm_parts.append(f"{key}: {facts[key]}")
    farm_note = "、".join(farm_parts) if farm_parts else None

    roast_hint = facts.get("焙煎度")

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": None,
        "unit_note": "生豆200gを焙煎(焙煎後の正確な重量表記なし)",
        "stock_status": status_label,
        "out_of_stock": not available,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    status_resp = requests.get(f"{BASE_URL}/data/beans-status.json", headers=REQUEST_HEADERS, timeout=20)
    status = status_resp.json().get("beans", {})

    records = []
    flavored_records = []
    for slug in SLUGS:
        try:
            detail = build_record(slug, status)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: slug={slug} ({e})")
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
    with open("data_jinenho.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jinenho.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
