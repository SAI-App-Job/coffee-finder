# -*- coding: utf-8 -*-
"""
scrape_wasedasanae.py

早苗(waseda-sanae.coffee、東京都新宿区戸塚町1-102、早稲田大学南門前の
喫茶・バー・自家焙煎珈琲豆焙煎販売店)の商品情報を取得する。Shopify製。
本体の店舗紹介サイト(waseda-sanae.com)とは別ドメインの専用オンライン
ショップ(waseda-sanae.coffee)で豆を販売しており、/products.jsonが
そのまま利用できる(2026-09確認)。

【店舗発見の経緯】
高田馬場・早稲田エリアの自家焙煎コーヒー豆店が本アプリに1件も収録されて
いないという利用者からの指摘を受けた総点検で発見(tailoredcafe.jpの
「高田馬場・早稲田のコーヒー豆おすすめ専門店10選」記事経由)。同記事では
「喫茶/ber 珈琲豆焙煎販売 早苗」と紹介されているが、公式サイト上の自称は
一貫して「早苗」のみのため、店名は「早苗」を採用した。

【カテゴリ判定について】
商品名だけでは判定できない自家製ブレンドが3種(「早苗スペシャルティ」
「浅煎りスペシャルティ」「試験前ブレンド」)あり、うち「試験前ブレンド」
以外の2種は商品名に「ブレンド」の文字を含まない。Shopifyのtags配列に
「オリジナルブレンド」(ブレンド3種)/「シングルオリジン」(産地別12種)/
「デカフェ（カフェインレス）」(1種)が明確に分かれて付与されていることを
実データ確認済みのため、tagsで「オリジナルブレンド」と判定できる商品は
category="ブレンド"に上書きする。

【「お試し」商品の除外について】
「初めての方限定商品「お試し　早苗スペシャルティ100g」」「同「お試し
浅煎りスペシャルティ100g」」の2点は、実データ確認したところ銘柄・重量・
価格(¥1,000/100g)のいずれも通常版の「早苗スペシャルティ」「浅煎り
スペシャルティ」と完全に一致しており、初回購入者向けの呼称違いの同一
商品と判断できる。通常版の方を採用し、お試し版は重複として除外する。

【body_htmlの構造について】
実データ確認済み(全16件で共通): 最初の<p>が「[短いテイスティング文]
<br><br>原産国: X<br>標高: Ym<br>精製: Z<br>[品種: W または 乾燥: V]
<br><br><strong>[利用シーン名]</strong>」、2番目の<p>がその産地・製法を
掘り下げた長文説明という2段構成。ラベル付きの行(原産国/精製)から
origin_country/processing_methodを抽出しつつ、flavor_notesは
AMBER COFFEE等と同じ方針でbody_html全文(スペック行込み)をそのまま
採用する(ラベル行を含んでいても、ordering/shipping等の無関係な定型文
混入は無いため全文をテイスティング情報として扱って問題ないと判断)。

【焙煎度について】
全商品が「浅煎り/中煎り/中深煎り/深煎り」(一部「浅煎り〜深煎り」の
3段階)を同一価格で選べる方式(実データ確認済み: 同一商品内の全バリアント
が同一price)。変数名に「(推奨)」が付く焙煎度が1つあり、これをroast_hint
として保持し、roast_level自体は選択式のためNoneのままroast_selectable=True
とする。

【重量について】
実データ確認済み: 通常16商品はShopifyのvariants[].gramsが100で商品名の
実際の重量(いずれも100g)と一致するため信頼できる(AMBER COFFEEのような
不一致は確認されなかった)。
"""

import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "早苗",
    "url": "https://waseda-sanae.com/",
    "platform": "Shopify(専用オンラインショップwaseda-sanae.coffeeの/products.jsonを利用。"
                "店舗紹介サイト本体はwaseda-sanae.comの別ドメイン)",
    "address": "東京都新宿区戸塚町1-102",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(Shopify標準テンプレートを想定。/products.json取得のみで購入操作は行わない)",
}

PRODUCTS_JSON_URL = "https://waseda-sanae.coffee/products.json?limit=250"
BASE_PRODUCT_URL = "https://waseda-sanae.coffee/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDE_TITLE_KEYWORDS = ["お試し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
RECOMMENDED_PATTERN = re.compile(r"^(.+?)（推奨）")

SPEC_LABEL_PATTERN = re.compile(r"^(原産国|標高|精製|品種|乾燥)[：:]\s*(.+)$")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_spec_lines(body_html: str) -> dict:
    """先頭<p>内の「ラベル: 値」形式の行(原産国/標高/精製/品種/乾燥)を辞書化する。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    first_p = soup.find("p")
    if not first_p:
        return {}
    text = first_p.get_text("\n", strip=True)
    result = {}
    for line in text.split("\n"):
        m = SPEC_LABEL_PATTERN.match(line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def extract_recommended_roast(variants: list[dict]) -> str | None:
    """バリアントタイトルの先頭要素(焙煎度)から「(推奨)」付きの値を探す。"""
    for v in variants:
        title = v.get("title") or ""
        roast_part = title.split(" / ")[0]
        m = RECOMMENDED_PATTERN.match(roast_part)
        if m:
            return m.group(1).strip()
    return None


def build_record(product: dict) -> dict:
    title = (product.get("title") or "").strip()
    tags = product.get("tags") or []
    variants = product.get("variants") or []
    product_url = f"{BASE_PRODUCT_URL}/{product.get('handle')}"

    parsed = parse_product(title)
    if "オリジナルブレンド" in tags:
        parsed["category"] = "ブレンド"

    specs = parse_spec_lines(product.get("body_html") or "")

    origin_note = specs.get("原産国")
    if origin_note:
        detected = detect_country_name(origin_note) or origin_note
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description"

    processing_note = specs.get("精製")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = specs.get("品種")

    price = None
    if variants:
        first_price = variants[0].get("price")
        price = int(float(first_price)) if first_price is not None else None

    weight_g = None
    if variants:
        grams = variants[0].get("grams")
        weight_g = grams if grams else None
    if not weight_g:
        m = WEIGHT_PATTERN.search(title)
        weight_g = int(m.group(1)) if m else None

    roast_hint = extract_recommended_roast(variants)

    structural_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, structural_out_of_stock)

    flavor_notes = BeautifulSoup(product.get("body_html") or "", "html.parser").get_text("\n", strip=True) or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast_hint,
        "roast_selectable": True,
        "variety": variety,
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def is_target_product(product: dict) -> bool:
    title = (product.get("title") or "").strip()
    if not title:
        return False
    if product.get("product_type") != "コーヒー豆":
        return False
    return not any(kw in title for kw in EXCLUDE_TITLE_KEYWORDS)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    target_products = [p for p in products if is_target_product(p)]

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in target_products:
        title = (product.get("title") or "").strip()
        product_url = f"{BASE_PRODUCT_URL}/{product.get('handle')}"
        variants = product.get("variants") or []
        current_price = int(float(variants[0]["price"])) if variants else None
        current_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title, price=current_price, out_of_stock=current_out_of_stock):
            records.append(prev)
            continue

        record = build_record(product)
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
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_wasedasanae.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_wasedasanae.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
