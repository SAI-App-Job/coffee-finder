# -*- coding: utf-8 -*-
"""
scrape_mameiri.py

豆煎人(mameiri.net、屋号「浜松自家焙煎 豆煎人(マメイリビト)」、
静岡県浜松市中央区原島町453-3、自家焙煎豆のオンライン販売)の商品情報を
取得する。WordPress + WooCommerce(ひつじ珈琲(scrape_hitsuji.py)と同じ
公開Store API方式)。

robots.txt確認済み(2026-09時点): /wp-admin/等の管理系パスのみDisallow
(admin-ajax.phpは個別にAllow)。本スクレイパーが使う公開APIエンドポイント
は制限対象外。

【APIエンドポイントのバージョンについて】
実データ確認済み: ひつじ珈琲(scrape_hitsuji.py)が使う
/wp-json/wc/store/v1/products はこの店舗では404(rest_no_route)になり
存在しない。/wp-json/ のルート一覧を確認したところ、このWooCommerce
バージョンでは/wp-json/wc/store/products(vなし)が実際に有効な公開
Store APIエンドポイントだった。店舗ごとにWooCommerce/店舗ページの
バージョンが異なりエンドポイントのバージョン接頭辞が違う場合がある
ため、新規にWooCommerce店舗のスクレイパーを書く際は/wp-json/で
実際に有効なルートを確認すること。

【重量について】
実データ確認済み: 商品名には重量が明記されず、short_description(実際は
description全文、全商品共通の定型文の中)に「販売価格は{N}g単位です。」
という一文がある。ほとんどの商品が200g単位だが、一部(ゲイシャ・
マイクロロット等の希少ロット)は100g単位。この一文から重量を抽出する
(名前ベースの重量抽出は使えないため店舗固有ロジック)。

【重量違いの重複について】
実データ確認済み: 全154件中、「イエメン 新母体品種 イエメニア」
「イエメン モカハラズ　バレルエイジド ナチュラル」の2銘柄のみ、
商品名末尾に「(100g)」が付く100g版と付かない200g版が別商品として
重複登録されている(価格はおよそ2倍)。商品名から「(100g)」表記を
除いた基準名でグルーピングし、実際の重量(descriptionから抽出)が
最小のものを代表として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 全154件中、マグカップ(猫印ミルク/九谷焼/SALIU/
ポーリッシュポタリー/フローラルパラダイス/デイジー等)・トリベット
(鍋敷き)・コースター(ソープストーン/波佐見焼/ラバー等)・
ダイエットスケール(DULTON)・キャニスター(LOLO SALIU)・
ミルクピッチャー・カップ&ソーサー(益子焼/九谷焼)・プレート(デイジー)・
郵送料(クリックポスト/レターパック各種/地域別配送料)が非コーヒー豆。
これらは店舗説明文に共通する「販売価格は{N}g単位です」の一文が無い
ことも確認済み(重量単位の記載がない=コーヒー豆でない、という副次的な
判定根拠にもなる)。また「小豆コーヒー」「黒大豆 珈琲」「大豆珈琲」は
コーヒー豆(Coffea)ではない代用コーヒー、「アイスコーヒー」は完成品の
液体飲料(生豆・焙煎豆ではない)のため、いずれも対象外として除外する。
「まかないコーヒー」(スタッフ用にブレンドされた実在の産地の組み合わせ)
は実在のコーヒー豆ブレンドのため対象に含める。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆煎人",
    "url": "https://mameiri.net/",
    "platform": "WooCommerce",
    "address": "静岡県浜松市中央区原島町453-3",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等の管理系パスのみDisallow。"
                          "本スクレイパーが使うStore API"
                          "(/wp-json/wc/store/products)は制限対象外)",
}

API_URL = "https://mameiri.net/wp-json/wc/store/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "郵送料", "マグ", "リベット", "鍋敷き", "コースター", "ダイエットスケール",
    "キャニスター", "ミルクピッチャー", "ソーサ", "プレート",
    "小豆コーヒー", "黒大豆", "大豆珈琲", "アイスコーヒー",
]
WEIGHT_DESC_PATTERN = re.compile(r"販売価格は.{0,10}?(\d+)\s*[gｇ]\s*単位")
NAME_WEIGHT_SUFFIX_PATTERN = re.compile(r"[\s　]*[（(]\s*\d+\s*[gｇ]\s*[)）]\s*")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return HTML_TAG_PATTERN.sub(" ", text or "")


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def parse_weight_g(description_html: str) -> int | None:
    text = strip_html(description_html)
    m = WEIGHT_DESC_PATTERN.search(text)
    return int(m.group(1)) if m else None


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = NAME_WEIGHT_SUFFIX_PATTERN.sub(" ", item["name"])
        base_name = re.sub(r"[\s　]+", " ", base_name).strip()
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        existing = by_base_name.get(base_name)
        if existing is None:
            by_base_name[base_name] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    name = item["name"]
    parsed = parse_product(name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(name, item["structural_out_of_stock"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

    candidate_items = []
    for product in products:
        name = (product.get("name") or "").strip()
        if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
            continue

        description_html = product.get("description") or ""
        weight_g = parse_weight_g(description_html)
        if weight_g is None:
            # 実データ確認済み: コーヒー豆商品には必ず「販売価格は{N}g単位です」の
            # 一文があり、無い商品は非コーヒー豆(NON_BEAN_KEYWORDSで拾い切れて
            # いない雑貨等)である可能性が高いため、安全側に倒して除外する。
            continue

        price = product.get("prices", {}).get("price")
        price = int(price) if price is not None else None

        candidate_items.append({
            "name": name,
            "weight_g": weight_g,
            "price": price,
            "url": product.get("permalink"),
            "structural_out_of_stock": not product.get("is_in_stock", True),
        })

    canonical_items = pick_canonical_items(candidate_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mameiri.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameiri.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
