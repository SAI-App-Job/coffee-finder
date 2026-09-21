# -*- coding: utf-8 -*-
"""
scrape_klatchcoffee.py

KLATCH COFFEE(石垣島カフェ、klatch-coffee.com、沖縄県石垣市大川200-1)の
商品情報を取得する。Shopify(/products.json全件取得方式)。

【住所・焙煎拠点について】
特定商取引法ページ(https://klatch-coffee.com/policies/legal-notice)で
「販売事業者の住所: 沖縄県石垣市大川200-1」を確認済み(2026-09時点)。
商品説明文(実データ確認済み)によれば、実際の焙煎は石垣島の西側にある
小浜島の焙煎所「Island Coffee Roastery」で行っている(自家焙煎の一部を
別の島の系列施設で行っている形態。候補リストの注記どおり自家焙煎として
対象に含める)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txt(AIエージェント向け
agents.md/UCPエンドポイントの案内を含む)。制限なし。

【単一Shopify商品を複数銘柄に分割することについて】
実データ確認済み: コーヒー豆は「コーヒー 豆/粉」という1つのShopify商品
(handle: c001)に、option1(銘柄: ブレンド/タンザニア/コスタリカ/デカフェ/
3種セット)×option2(挽き方×重量: 豆(240g)/粉(240g)/豆(80g)/粉(80g))の
組み合わせバリアントとして登録されている。option1の銘柄ごとに別商品として
分割し、それぞれ「豆」×最小重量(80g)を代表バリアントとして採用する
(重量違い商品の代表選択と同じ考え方)。「3種セット」はブレンド+タンザニア+
コスタリカの詰め合わせで単品と重複するため除外する。「デカフェ」は産地の
記載が商品説明文にも無く(実データ確認済み)、産地不明のため構造的チェックで
非コーヒー豆として除外される(産地不明・ブレンド表記なしの一般ルール)。

【非コーヒー豆商品の除外について】
実データ確認済み(全29件のShopify商品): コーヒー豆(c001)以外は、Coming Soon
(未公開ダミー商品、複数件)・ミスト/石鹸(アロマ雑貨)・プレゼントセット・
ドリップバッグ・オリジナルステッカー・Hydro Flask水筒・Fugerコーヒーアート・
フェイスタオル/バスタオル/サウナハット/Tシャツ/サンダル(グッズ)・カフェオレ
ベース(リキッド)・マグカップ各種・サコッシュが該当し、すべて非対象。
コーヒー豆(c001)のみを対象として個別に処理する。

【flavor_notes(2026-09-22追記)】
実データ確認済み: products.json側のbody_htmlは全銘柄共通の店舗紹介文
(海のそばで焙煎している旨等)のみで銘柄別のテイスティング情報を含まない。
一方、商品ページ(https://klatch-coffee.com/products/c001)本体には
産地情報とは別のdiv.description(2つ目、【コーヒーの種類】見出し配下)に
「ISLAND BLEND（ブレンド）」「ISLAND COFFEE（タンザニア）」「ISLAND
COFFEE PREMIUM（コスタリカ）」「DECAF COFFEE（メキシコ）」の見出し
(h5)ごとに産地・Farm・Flavor・酸味/苦味/コクの星評価とテイスティング文
が構造化されている。見出しのテキストに銘柄名(ブレンド/タンザニア/
コスタリカ)が括弧書きで含まれるため、見出し文字列に銘柄名が含まれるかで
突合する。デカフェは既存の除外ルール(産地不明・ブレンド表記なし)により
本スクレイパーの対象外のままのため、flavor_notesの突合対象にも含めない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "KLATCH COFFEE",
    "url": "https://klatch-coffee.com/",
    "platform": "Shopify",
    "address": "沖縄県石垣市大川200-1",
    "prefecture": "沖縄県",
    "robots_txt_status": "許可(2026-09確認。Shopify標準のrobots.txtで制限なし)",
}

PRODUCTS_JSON_URL = "https://klatch-coffee.com/products.json?limit=250"
PRODUCT_HANDLE = "c001"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_VARIETY_KEYWORDS = ["セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_coffee_product() -> dict | None:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    for product in resp.json().get("products", []):
        if product.get("handle") == PRODUCT_HANDLE:
            return product
    return None


def fetch_variety_flavor_notes() -> dict[str, str]:
    """商品ページ本体の銘柄別description(理由はモジュールdocstring参照)を
    見出し(h5)ごとに分割し、見出し文字列をキーとした辞書で返す。"""
    resp = requests.get(f"https://klatch-coffee.com/products/{PRODUCT_HANDLE}",
                         headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    desc_divs = soup.select("div.description")
    if len(desc_divs) < 2:
        return {}
    notes: dict[str, str] = {}
    heading = None
    parts: list[str] = []
    for el in desc_divs[1].find_all(["h5", "p"], recursive=False):
        if el.name == "h5":
            if heading:
                notes[heading] = "\n".join(p for p in parts if p)
            heading = el.get_text(strip=True)
            parts = []
        else:
            text = el.get_text("\n", strip=True)
            if text:
                parts.append(text)
    if heading:
        notes[heading] = "\n".join(p for p in parts if p)
    return notes


def match_flavor_notes(variety: str, notes_by_heading: dict[str, str]) -> str | None:
    for heading, text in notes_by_heading.items():
        if variety and variety in heading:
            return text
    return None


def pick_canonical_variants(product: dict) -> list[dict]:
    """option1(銘柄)ごとにグルーピングし、「豆」×最小重量を代表として選ぶ
    (理由はモジュールdocstring参照)。"""
    by_variety: dict[str, tuple[int, dict]] = {}
    for variant in product.get("variants", []):
        variety = (variant.get("option1") or "").strip()
        option2 = variant.get("option2") or ""
        if not variety or any(kw in variety for kw in NON_BEAN_VARIETY_KEYWORDS):
            continue
        weight_m = WEIGHT_PATTERN.search(option2)
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        is_ground = "粉" in option2
        # 「豆」を優先するため、粉バリアントには大きなペナルティを加える
        sort_key = weight_key + (100000 if is_ground else 0)
        existing = by_variety.get(variety)
        if existing is None or sort_key < existing[0]:
            by_variety[variety] = (sort_key, variant)
    return [v for _key, v in by_variety.values()]


def build_record(product: dict, variant: dict, notes_by_heading: dict[str, str]) -> dict | None:
    variety = (variant.get("option1") or "").strip()
    option2 = variant.get("option2") or ""
    raw_name = f"{product['title']} {variety} {option2}".strip()
    # 実データ確認済み: 銘柄違いが1つのShopify商品のバリアントとして登録されて
    # いるため、product_urlをhandleだけにすると全銘柄が同一URL(=同一ID)になり
    # aggregate_shops.py側でID衝突が起きる(既知のバグパターン)。Shopify公式の
    # バリアント選択URL形式(?variant=<variant_id>)を使い、銘柄ごとに一意な
    # 実在するURLを割り当てる。
    product_url = f"https://klatch-coffee.com/products/{product['handle']}?variant={variant['id']}"

    parsed = parse_product(variety)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    parsed = apply_category_hint_fallback(parsed, None)

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "product_url": product_url,
        }

    price = int(float(variant["price"])) if variant.get("price") is not None else None
    weight_m = WEIGHT_PATTERN.search(option2)
    weight_g = int(weight_m.group(1)) if weight_m else None

    structural_out_of_stock = variant.get("available") is False
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": match_flavor_notes(variety, notes_by_heading),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    product = fetch_coffee_product()
    if not product:
        print("[warn] コーヒー豆商品(c001)が見つかりません")
        return [], [], []

    notes_by_heading = fetch_variety_flavor_notes()

    records = []
    flavored_records = []
    non_bean_records = []
    for variant in pick_canonical_variants(product):
        detail = build_record(product, variant, notes_by_heading)
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_klatchcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_klatchcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
