# -*- coding: utf-8 -*-
"""
scrape_rhizomag.py

Rhizomag(rhizomag.shop-pro.jp、カラーミーショップ/shop-pro.jp)の商品情報を
取得する。神奈川県川崎市多摩区(宿河原)の単独店舗。

scrape_roastdesign.pyをテンプレートに実装しているが、同じshop-pro.jpでも
店舗が選んだテーマはPHILOCOFFEA/Roast Design Coffeeいずれとも異なる(実データ
確認済み、2026-08時点)。共通しているのはURLクエリの体系(?mode=srh / ?pid=)と
`var Colorme = {...}`に埋め込まれた商品JSONのみ。

【文字コードについて】
実データ確認済み: レスポンスヘッダがcharset=EUC-JP(Content-Type: text/html;
charset=EUC-JP)。requestsの自動判定に任せず、明示的にresp.encoding="euc-jp"を
設定する。

【この店舗の特徴: コーヒー豆はごく一部】
実データ確認済み(2026-08時点、全73件): HARIO・ザッセンハウス(コーヒーミル)・
「Bボトル」(水筒ブランド)等の器具・雑貨、チョコレート菓子、水出し珈琲バッグ・
珈琲バッグ(ドリップバッグ)の詰め合わせ・福袋的な「SET」「BOX」商品が大半を
占め、単一産地のストレート豆は15件程度に留まる。除外は以下の二段構えで行う:
  1. NON_BEAN_KEYWORDS: 商品名に基づく一覧段階での除外。水出し(コールドブリュー)・
     ドリップバッグ・詰め合わせSET/BOXは、コーヒー豆そのものではなく別の加工・
     梱包形態の商品としてPHILOCOFFEA/Roast Design Coffeeの方針を踏襲し除外する。
  2. 構造的チェック(parse_product_detail内): 商品説明文の「原産国：」表記も
     商品名からの産地国も無く、ブレンド判定でもない商品は、器具・雑貨・食品等の
     コーヒー豆ではない商品とみなして除外する(実データ確認済み: HARIO/
     ザッセンハウス/Bボトル等はいずれも「原産国」に該当する記述を持たない)。

【商品説明文の「原産国：」について】
div.p-product-explain__body内に「原産国：インドネシア」「推奨焙煎：
イタリアンロースト（深煎り）」のような自由記述で構造化されている。ただし
「ARIGATO BOX」等の複数産地の詰め合わせ商品は「◯原産国：タンザニア」
「◯原産国：ニカラグア」のように複数回出現することを実データで確認済み
(該当商品はNON_BEAN_KEYWORDSで一覧段階で除外されるが、保険として詳細ページ
パース側でも「原産国」が複数回出現する場合は単一産地として扱わない)。

【バリアント(重量×挽き方)について】
1商品につき重量(200g/300g/400g/500g等)×挽き方(豆/紙フィルター用等)の組み合わせで
最大16バリアントを持つ(実データ確認済み)。挽かない「豆」を優先し、その中で
最小重量のものを代表として採用する(珈琲丸のpick_canonical_variant()と同じ考え方)。

【在庫について】
実データ確認済み: 商品JSONのinventory_controlが"none"で、stock_num はどの
商品・バリアントも常にnullだった。構造化された在庫フラグは実質的に機能して
いないため、商品名のテキストのみで在庫状態を判定する(Roast Design Coffeeの
stock_num運用とは異なる)。

robots.txt確認済み(2026年8月時点): PHILOCOFFEA/Roast Design Coffeeと同一の
記述(User-agent: * は/secure/と/cart/のみ制限)。

【差分ベーススクレイピング】一覧ページ(軽量)の時点で商品名・価格・在庫状況が
前回(data/products.json)と変わっていない商品は、詳細ページの再取得をスキップ
して前回のレコードをそのまま使い回す(previous_data.py参照)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Rhizomag",
    "url": "https://rhizomag.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県川崎市多摩区宿河原7-14-13 毬ビル102",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA/Roast Design Coffeeと同一の記述)",
}

CRAWL_DELAY_SECONDS = 3
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://rhizomag.shop-pro.jp/"
LIST_BASE_URL = "https://rhizomag.shop-pro.jp/?mode=srh&keyword=&sort=n"

# 水出し(コールドブリュー)・ドリップバッグの詰め合わせ・福袋的なSET/BOX商品は、
# コーヒー豆そのものではなく別の加工・梱包形態の商品として除外する(実データ確認済み。
# 「ARIGATO BOX」「ZEITAKU BOX」「◯◯set」「初回限定SET」「珈琲バック」「珈琲bag」等)。
# 大文字小文字を区別せず判定する。
NON_BEAN_KEYWORDS = [
    "水出し", "コールドブリュー", "cold brew", "set", "box", "セット", "珈琲バック", "珈琲bag",
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
LIST_PRICE_PATTERN = re.compile(r"^([\d,]+)円")
DESC_ORIGIN_PATTERN = re.compile(r"原産国[：:]\s*([^\n]+)")
DESC_ROAST_PATTERN = re.compile(r"推奨焙煎[：:]\s*([^\n]+)")
DESC_FEATURE_PATTERN = re.compile(r"特徴[：:]\s*([^\n]+)")
VARIANT_WEIGHT_PATTERN = re.compile(r"(\d+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """重量×挽き方の組み合わせバリアントから代表の1件を選ぶ。挽かない「豆」を
    優先し、その中で最小重量のものを採用する(珈琲丸と同じ考え方)。"""
    if not variants:
        return None

    def weight_key(v):
        m = VARIANT_WEIGHT_PATTERN.search(v.get("option1_value") or "")
        return int(m.group(1)) if m else float("inf")

    whole_bean = [v for v in variants if v.get("option2_value") == "豆"]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def parse_description_fields(description_text: str) -> dict:
    """div.p-product-explain__body(<br>を改行に置換済み)から原産国・推奨焙煎・
    特徴を抽出する。「原産国：」が複数回出現する場合は、ARIGATO BOX等の複数産地
    詰め合わせ商品とみなし、単一産地として扱わない(NON_BEAN_KEYWORDSをすり抜けた
    場合の保険)。"""
    origin_matches = DESC_ORIGIN_PATTERN.findall(description_text)
    roast_m = DESC_ROAST_PATTERN.search(description_text)
    feature_m = DESC_FEATURE_PATTERN.search(description_text)
    return {
        "origin": origin_matches[0].strip() if len(origin_matches) == 1 else None,
        "roast_hint": roast_m.group(1).strip() if roast_m else None,
        "feature": feature_m.group(1).strip() if feature_m else None,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)

    raw_name = ""
    variants = []
    if colorme_product:
        # var Colorme のnameは<script>内のJSON文字列値であり、fetch_page()の
        # soup.find_all("br")によるDOM上の<br>置換が効かない(実データ確認済み:
        # "インドネシア<br>マンデリン ミトラ G1"のようにリテラル文字列"<br>"を
        # そのまま含む)。ここで明示的に置換する。
        raw_name = (colorme_product.get("name") or "").replace("<br>", " ").replace("\n", " ").strip()
        variants = colorme_product.get("variants") or []
    if not raw_name:
        name_el = soup.select_one("h1, div.p-product-detail-head__name")
        raw_name = name_el.get_text(strip=True) if name_el else ""

    stock_num = colorme_product.get("stock_num") if colorme_product else None
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "stock_status": stock_status,
            "product_url": url,
        }

    body_el = soup.select_one("div.p-product-explain__body")
    description_text = body_el.get_text() if body_el else ""
    fields = parse_description_fields(description_text)

    if fields["origin"]:
        country = detect_country_name(fields["origin"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    # 産地情報(説明文の原産国)、商品名からの産地国、ブレンド判定のいずれも
    # 存在しない場合のみ、コーヒー豆商品ではない(器具・雑貨・食品等)とみなして
    # 除外する(Roast Design Coffeeと同じ構造的チェック)。
    if not fields["origin"] and not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "stock_status": stock_status,
            "product_url": url,
        }

    parsed = apply_category_hint_fallback(parsed, None)

    # 「推奨焙煎」は店舗の参考表示であり、備考欄で変更依頼が可能なことが実データで
    # 確認済みのため、roast_levelではなくroast_hintとして保持する(下のreturn参照)。

    variant = pick_canonical_variant(variants)
    weight_g = None
    price = None
    if variant:
        m = VARIANT_WEIGHT_PATTERN.search(variant.get("option1_value") or "")
        weight_g = int(m.group(1)) if m else None
        price = variant.get("option_price_including_tax")

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
        "roast_hint": fields["roast_hint"],
        # 推奨焙煎とは別に、備考欄で希望の焙煎度を指定できることが実データで確認済み
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "flavor_notes": fields["feature"],
        "blend_components": [],  # 実データではブレンド商品(単一バッグ)の例が見つからず未対応
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "product_url": url,
    }


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.prd-lst-unit")

    results = []
    for item in items:
        name_link_el = item.select_one("p.prd-lst-name a")
        price_el = item.select_one("p.prd-lst-price")

        if not name_link_el:
            continue

        raw_name = name_link_el.get_text(strip=True)
        href = name_link_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_match = LIST_PRICE_PATTERN.search(price_text)
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_status = detect_stock_status(raw_name)

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
        })
    return results


def scrape_all_products(fetch_details: bool = True, max_pages: int = 50) -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = []
    for page in range(1, max_pages + 1):
        items = scrape_product_list_page(page)
        if not items:
            break
        items = [
            i for i in items
            if not any(kw.lower() in i["raw_name"].lower() for kw in NON_BEAN_KEYWORDS)
        ]
        all_list_items.extend(items)
        time.sleep(CRAWL_DELAY_SECONDS)

    if not fetch_details:
        return all_list_items, [], []

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = detail["stock_status"] != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_rhizomag.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_rhizomag.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
