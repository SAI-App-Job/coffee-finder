# -*- coding: utf-8 -*-
"""
scrape_acecoffee.py

ACE COFFEE ROASTER(ace-coffee.shop-pro.jp、札幌市豊平区平岸3条13丁目7-18
第二平岸メインハイツ、カラーミーショップ/shop-pro.jp)の商品情報を取得する。

【住所について】
候補リストでは特定商取引法ページの取得結果が「南13条西7-18」「北33条西
7-18」の間で不一致だったが、再取得(https://ace-coffee.shop-pro.jp/?mode=sk)
した結果、正しい住所は「〒062-0933 札幌市豊平区平岸三条13丁目7-18
第二平岸メインハイツ」だった(2026-09確認)。以前の不一致は取得時の読み取り
誤りと考えられる。

【商品一覧について】
実データ確認済み: 全商品9件が1ページに収まる小規模店舗(?mode=srh&cid=&keyword=
で全件検索)。7件が単一銘柄のブレンド/ストレート(200g)、2件が複数銘柄の
セット(「3つのブレンドセット」「4種のシングルオリジン セット」)のため
NON_BEAN_KEYWORDSで除外する。

【プラットフォームについて】
RITARU COFFEE等と同じくprd_lst_*クラスを使わない別テーマのため、一覧は
pidリンクのみ取得し、価格・重量は商品詳細ページのvar Colorme JSONから
取得する。

robots.txt確認済み(2026-09時点): 他のshop-pro.jp系店舗と同一の記述。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:description/meta descriptionは約100文字に切り
詰められており使用できない。代わりに商品詳細ページのdiv.product-order-exp
内に、対象7件全てで焙煎士自身によるテイスティング文+ブレンド構成が
入っていることを確認した。末尾に「□おすすめの抽出レシピ」という見出し
から抽出レシピの手順が続くため、この見出しの直前で打ち切る。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ACE COFFEE ROASTER",
    "url": "https://ace-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市豊平区平岸3条13丁目7-18 第二平岸メインハイツ",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。他のshop-pro.jp系店舗と同一の記述。"
                          "User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://ace-coffee.shop-pro.jp/"
ALL_ITEMS_URL = "https://ace-coffee.shop-pro.jp/?mode=srh&cid=&keyword="
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["セット"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"□?\s*おすすめの抽出レシピ")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.product-order-exp")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()]
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(url: str) -> list[dict]:
    soup = fetch_page(url)
    results = []
    seen_pids = set()
    for a in soup.select('a[href*="pid="]'):
        text = a.get_text(strip=True)
        href = a.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not text or not m:
            continue
        pid = m.group(1)
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        results.append({"raw_name": text, "product_url": f"{BASE_URL}?pid={pid}"})
    return results


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


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        for key in ("option1_value", "option2_value"):
            m = WEIGHT_PATTERN.search(variant.get(key) or "")
            if m:
                return int(m.group(1))
    m = WEIGHT_PATTERN.search(fallback_text or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def is_whole_bean(v):
        return "豆のまま" in (v.get("option1_value") or "") or "豆のまま" in (v.get("option2_value") or "")

    whole_bean = [v for v in variants if is_whole_bean(v)]
    return (whole_bean or variants)[0]


def build_record(product_url: str, fallback_title: str) -> dict | None:
    if any(kw in fallback_title for kw in NON_BEAN_KEYWORDS):
        return None

    soup = fetch_page(product_url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": fallback_title,
            "non_bean": True,
            "product_url": product_url,
        }

    variants = colorme_product.get("variants") or []
    title = (colorme_product.get("name") or fallback_title).strip()
    parsed = parse_product(title)
    variant = pick_canonical_variant(variants)

    # 実データ確認済み: 本店舗のテーマはvariantsが常に空配列で、価格は
    # product直下のsales_price_including_taxに単一価格として入る
    # (挽き方等の選択バリアントが無い、実質単一形態の商品)。
    price = (
        variant.get("option_price_including_tax") if variant
        else colorme_product.get("sales_price_including_tax")
    )
    # 実データ確認済み: stock_numは全商品で一律0(在庫管理機能を使っていないと
    # 見られる、shop-pro系の「常にnull」パターンと同様の実質未運用)。
    # 構造化フラグとしては使わず、商品名のテキストのみで在庫判定する。

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_from_variant(variant, title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = scrape_list_page(ALL_ITEMS_URL)

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        try:
            detail = build_record(item["product_url"], item["raw_name"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        if detail is None:
            continue

        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_acecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_acecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
