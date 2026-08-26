# -*- coding: utf-8 -*-
"""
scrape_atsugicoffee.py

厚木珈琲(atsugicoffee.com、神奈川県厚木市、Shopify製)の商品情報を取得する。
グアテマラに自社農園「ATSUGI COFFEE FARM」を持つのが特色。

robots.txt確認済み(2026-08時点): Shopify標準の生成robots.txtで、
「Public product, collection, page, blog, policy, cart, and localized HTML
is crawlable」と明記されている。/products/・/collections/は許可対象
(User-agent: *にAllow: /、/cart/・/checkout・/account等のみDisallow)。
AIエージェント向けの購入自動化に関する注意書きもあるが、本スクレイパーは
商品情報の読み取りのみで購入操作は一切行わないため無関係。

【対象コレクションについて】実データ確認済み(2026-08時点):
トップページのナビゲーションに /collections/beans(対象)・/collections/
drip-bag(対象外)・/collections/gift(対象外)・/collections/liquid(対象外)・
/collections/pickup が存在。指示通りBeansコレクションのみを対象にする
(collections/beans/products.jsonで直接絞り込める)。

【Beansコレクション内の除外対象について】実データ確認済み(2026-08時点):
Beansコレクション自体にも豆売り本来の商品ではないものが混在していた
(全15件中6件が対象外):
  - 「初回限定 お試しセット」「ATUSGI COFFE FARM飲み比べセット(50g×3種)」:
    複数銘柄の詰め合わせ(セット)
  - 「お得な定期便 | 毎月お届け200gコース」: 定期便プラン(特定の銘柄を
    指さない)
  - 「【生豆】ATSUGI COFFEE FARM/Washed・Honey・Natural」: 焙煎前の生豆を
    1kg〜10kg単位で販売する別カテゴリの商品(他の自家焙煎店で扱う「飲むための
    焙煎豆」とは性質が異なり、英語ラベル(Country/Farm/Producer/Altitude等)の
    別フォーマットで書かれている)
商品名に「セット」「定期便」「生豆」のいずれかを含む商品を除外することで
これら6件を除き、実際に飲用の焙煎豆9件(ATSUGI COFFEE FARM 4種・ブレンド3種・
AMIGO・DECAFE)が残る。

【商品説明(body_html)の構造について】実データ確認済み(2026-08時点):
h2見出しで区切られたセクション内に「◯ラベル：値」または「○ラベル：値」
(U+25EF LARGE CIRCLEとU+25CB WHITE CIRCLEの2種類の丸記号が商品によって
混在している)という形式の<p>タグが並ぶ、非常に構造化された説明文になっている。
27coffeeのようなh2セクション単位の解析は不要で、body_html全体から
「[◯○]ラベル：値」パターンの行をすべて拾えば良い(このパターンに
マッチしない、値の無い箇条書き(「◯初めて厚木珈琲を飲む方」等)は「：」を
含まないため自然に除外される)。ただしDECAFEのように、複数行(複数ラベル)が
別々の<p>タグではなく同じ<p>タグ内に<br>区切りで詰め込まれている商品も
あった(実データ確認済み)。単純に<p>タグ単位でテキストを取り出すと複数行が
連結されてしまい1つ目のラベル以降が値に巻き込まれるため、<br>を改行に
変換したうえで行ごとにパターンマッチする方式にしている。
ラベル名は商品によって表記ゆれがある(自社農園の直営ロットは「生産地」、
複数農園のコミュニティロット(AMIGO)は「生産国」。精製方法も「精製」と
「精製方法」の両方が実データで見つかった)ため、両方の表記を拾う。
「フレーバー」「焙煎度」ラベルはブレンドも含めほぼ全商品に存在し、
flavor_notes・roast_hintとして高精度に取得できる。

【重量の扱いについて】
Shopify商品のvariant.gramsフィールドは全商品・全バリアントで0固定
(実データ確認済み、信頼できない)。重量はバリアントのtitle文字列
(例:「100g / 豆のまま」「豆のまま / 500g」のように語順が商品によって
不統一)から正規表現で抜き出す。「1Kg」「1kg」という大文字小文字混在の
表記もあるため、大文字小文字を無視してg/kgの両方に対応し、kgはgに換算する。

【デカフェの検出について】
「DECAFE」という商品はタイトルに「カフェインレス」「デカフェ」という
語を含まない(商品名は英語で"DECAFE"のみ)ため、通常のタイトルベースの
デカフェ検出(他店舗と同じ)に加えて本文(body_html)中の「カフェインレス」
「デカフェ」「DECAFE」も確認する。
"""

import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "厚木珈琲",
    "url": "https://atsugicoffee.com/",
    "platform": "Shopify(collections/beans/products.jsonエンドポイントを利用)",
    "address": "神奈川県厚木市飯山837-20",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。Shopify標準robots.txt。「products/collections等はクロール可能」と明記)",
}

BASE_URL = "https://atsugicoffee.com"
COLLECTION_HANDLE = "beans"
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDE_TITLE_KEYWORDS = ["セット", "定期便", "生豆"]

# ◯(U+25EF)・○(U+25CB)どちらの丸記号も実データで確認済み。値の無い箇条書きは
# 「：」を含まないため、この正規表現には自然にマッチしない。
LABEL_PATTERN = re.compile(r"^[◯○]([^：]+)：\s*(.+)$")

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.IGNORECASE)
DECAF_TRIGGER_PATTERN = re.compile(r"カフェインレス|デカフェ|DECAFE", re.IGNORECASE)


def parse_label_fields(body_html: str) -> dict:
    """body_html中の「◯ラベル：値」形式の行をすべてラベル→値の辞書にする。

    多くの商品では1行(1ラベル)ごとに別々の<p>タグに分かれているが、DECAFE等
    一部商品では複数行が同じ<p>タグ内に<br>区切りで詰め込まれていた(実データ
    確認済み)。<br>を改行に変換してから行単位でパターンマッチすることで、
    <p>タグの分かれ方に関わらず正しく1行=1ラベルとして拾えるようにしている。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    labels = {}
    for p in soup.select("p"):
        for line in p.get_text().split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            m = LABEL_PATTERN.match(line)
            if m:
                labels[m.group(1).strip()] = m.group(2).strip()
    return labels


def parse_weight_from_variant_title(variant_title: str | None) -> int | None:
    if not variant_title:
        return None
    m = WEIGHT_PATTERN.search(variant_title)
    if not m:
        return None
    value = float(m.group(1))
    grams = value * 1000 if m.group(2).lower() == "kg" else value
    return int(grams)


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """在庫があるバリアントの中で最小重量(タイトル文字列から解析)のものを優先し、
    無ければ全バリアント中最小重量のものを使う。gramsフィールドは全商品で0固定
    のため使用しない(実データ確認済み)。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants
    return min(
        pool,
        key=lambda v: parse_weight_from_variant_title(v.get("title")) or float("inf"),
    )


def detect_decaf_process(title: str, body_text: str) -> str | None:
    if not DECAF_TRIGGER_PATTERN.search(title) and not DECAF_TRIGGER_PATTERN.search(body_text):
        return None
    if "ウォータープロセス" in body_text:
        return "ウォータープロセスによりカフェインを除去"
    return "デカフェ(除去方法の詳細記載なし)"


def fetch_collection_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/collections/{COLLECTION_HANDLE}/products.json"
    resp = requests.get(url, params={"limit": 250, "page": page}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_target_product(product: dict) -> bool:
    title = product.get("title", "")
    return not any(kw in title for kw in EXCLUDE_TITLE_KEYWORDS)


def build_record(product: dict) -> dict:
    title = product.get("title", "")
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])) if variant else None,
            "product_url": product_url,
        }

    body_html = product.get("body_html", "")
    body_text = BeautifulSoup(body_html, "html.parser").get_text(" ")
    labels = parse_label_fields(body_html)

    origin_label = labels.get("生産地") or labels.get("生産国")
    if origin_label:
        detected = detect_country_name(origin_label) or origin_label
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    processing_label = labels.get("精製") or labels.get("精製方法")
    if processing_label:
        parsed["processing_method"] = normalize_processing_method(processing_label)

    variant = pick_canonical_variant(product.get("variants", []))
    structural_out_of_stock = not any(v.get("available") for v in product.get("variants", []))
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "roast_hint": labels.get("焙煎度"),
        "roast_selectable": False,  # 実データ確認済み: セレクトは挽き方(豆のまま/粉にする)のみ
        "farm_name": labels.get("農園"),
        "variety": labels.get("栽培品種"),
        "flavor_notes": labels.get("フレーバー"),
        "decaf_process": detect_decaf_process(title, body_text),
        "price": int(float(variant["price"])) if variant else None,
        "weight_g": parse_weight_from_variant_title(variant.get("title")) if variant else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_raw = []
    page = 1
    while True:
        batch = fetch_collection_page(page)
        if not batch:
            break
        all_raw.extend(batch)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    target_products = [p for p in all_raw if is_target_product(p)]

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in target_products:
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
        variant = pick_canonical_variant(product.get("variants", []))
        current_price = int(float(variant["price"])) if variant else None
        current_out_of_stock = not any(v.get("available") for v in product.get("variants", []))

        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=product.get("title", ""),
            price=current_price,
            out_of_stock=current_out_of_stock,
        ):
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

    with open("data_atsugicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_atsugicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
