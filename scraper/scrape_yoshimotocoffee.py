# -*- coding: utf-8 -*-
"""
scrape_yoshimotocoffee.py

自家焙煎珈琲 ヨシモトコーヒー(ycoffee.base.shop、沖縄県沖縄市知花5-35-6、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(白ラベルドメイン)。

【住所について】
特定商取引法ページ(https://ycoffee.base.shop/law)で実際に確認したところ
「事業者の名称: 吉本幸司 / 事業者の所在地: 〒904-2143 沖縄県沖縄市知花5-35-6」
であることを確認した(2026-09時点)。候補リストの住所と一致し、BASE社の
プロキシ住所(東京)ではない出店者本人の住所であることを確認済み。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等の既定UAは個別にDisallow: /指定があるが、User-agent: *
ルールでは/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外は
Allow: /。本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: sitemap.xmlから全46件の商品URLを取得し、各詳細ページの
`application/ld+json`(schema.org Product)から商品名・説明文・価格・在庫状況
(availability)を取得する(他のBASE系店舗のOGPタグ方式より説明文まで一括で
取得できるため、この店舗ではld+jsonを採用)。

【非コーヒー豆商品の除外について】
実データ確認済み(全46件): オリジナルドリップバッグ作成サービス(自由入稿の
オリジナルデザインパッケージ含む)・沖縄県産ブレンドドリップバック・
コザプレミアムドリップバック・入学祝ドリップ・ドリップセット・生豆(自家焙煎前の
未焙煎豆、3件)・コーヒーギフトセット・Kalita器具(ドリッパー/フィルター)が
コーヒー豆本体ではない商品として存在する。NON_BEAN_KEYWORDSでの一覧段階の除外に
加え、構造的チェック(産地国も産地情報(説明文の「○○産。」)も無く、ブレンド判定
でもない商品は除外)も保険として適用する。「イタリアンロースト 200g」のように
産地・ブレンドいずれの表記も無い商品(エスプレッソ用ロースト、実データ確認済み)は
この構造的チェックにより非コーヒー豆(産地不明)として除外される。

【産地について】
「モカ」「チャンチャマイヨ」のように商品名だけでは国名を特定できない銘柄も、
詳細ページの説明文冒頭に「エチオピア産。」「ペルー産。」のように明記されている
(実データ確認済み)。商品名からの国名検出に失敗した場合、説明文からの検出を
フォールバックとして使う。

【重量の重複について】
実データ確認済み: 「オリジナルブレンド300ｇ（豆）」「オリジナルブレンド300ｇ
（粉）」のように、同一銘柄・同一重量で挽き方(豆/粉)違いの商品が別商品として
登録されている例が1件ある。挽かない「豆」を優先して代表を選ぶ(他店舗と同じ
考え方)。「コザプレミアム100ｇ×4袋」のような複数袋セットは、1商品として
販売される内容量の合計(100g×4=400g)をweight_gとする。

【在庫について】
実データ確認済み: ld+jsonのoffers.availabilityが"https://schema.org/InStock"/
"https://schema.org/SoldOut"で構造化されている(「沖縄県産ブレンドドリップバック
10ｇ×10個」がSoldOutの実例で確認済み)。商品名のテキスト+この構造化フラグの
組み合わせで在庫状態を判定する。
"""

import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎珈琲 ヨシモトコーヒー",
    "url": "https://ycoffee.base.shop/",
    "platform": "BASE",
    "address": "沖縄県沖縄市知花5-35-6",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://ycoffee.base.shop"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 実データ確認済み(理由はdocstring参照)
NON_BEAN_KEYWORDS = [
    "ドリップ", "パッケージ", "セット", "ギフト", "生豆", "kalita", "Kalita",
]

LD_JSON_PATTERN = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
BAG_WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*[×xX]\s*(\d+)\s*[袋個]")
SIMPLE_WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
GRIND_SUFFIX_PATTERN = re.compile(r"[（(](豆|粉)[）)]\s*\Z")


def fetch_sitemap_urls() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def fetch_ld_json(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    m = LD_JSON_PATTERN.search(resp.text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_weight(title: str) -> int | None:
    m = BAG_WEIGHT_PATTERN.search(title)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m2 = SIMPLE_WEIGHT_PATTERN.search(title)
    return int(m2.group(1)) if m2 else None


def normalize_base_name(title: str) -> str:
    return GRIND_SUFFIX_PATTERN.sub("", title).strip()


def pick_canonical_items(items: list[dict]) -> list[dict]:
    """挽き方(豆/粉)違いで同一銘柄・同一重量の商品が別登録されている場合、
    挽かない「豆」を優先して代表を選ぶ(実データ確認済み: オリジナルブレンド300g)。"""
    by_base_name: dict[str, dict] = {}
    for item in items:
        base = normalize_base_name(item["raw_name"])
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_is_bean = "（粉）" not in existing["raw_name"] and "(粉)" not in existing["raw_name"]
        if not existing_is_bean and ("（粉）" not in item["raw_name"] and "(粉)" not in item["raw_name"]):
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    description = item.get("description") or ""
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item.get("price"),
            "product_url": item["product_url"],
        }

    if not parsed["origin_country"] and parsed["category"] != "ブレンド":
        # 商品名に国名が無い銘柄(モカ・チャンチャマイヨ等)は、詳細ページの説明文
        # 冒頭「○○産。」から補完する(実データ確認済み)
        country = detect_country_name(description)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    parsed = apply_category_hint_fallback(parsed, None)

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title, item.get("out_of_stock", False))

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": extract_weight(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    urls = [u for u in fetch_sitemap_urls() if "/items/" in u]

    raw_items = []
    for url in urls:
        try:
            data = fetch_ld_json(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not data:
            print(f"[warn] ld+jsonが見つかりません: {url}")
            continue

        title = (data.get("name") or "").strip()
        if not title or any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
            time.sleep(CRAWL_DELAY_SECONDS)
            continue

        offers = data.get("offers") or {}
        price = int(float(offers["price"])) if offers.get("price") is not None else None
        out_of_stock = offers.get("availability") not in (
            "http://schema.org/InStock", "https://schema.org/InStock",
        )

        raw_items.append({
            "raw_name": title,
            "description": data.get("description"),
            "price": price,
            "out_of_stock": out_of_stock,
            "product_url": url,
        })
        time.sleep(CRAWL_DELAY_SECONDS)

    canonical_items = pick_canonical_items(raw_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in canonical_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev, raw_name=item["raw_name"], price=item.get("price"),
        ):
            records.append(prev)
            continue

        detail = build_record(item)
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
    with open("data_yoshimotocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yoshimotocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
