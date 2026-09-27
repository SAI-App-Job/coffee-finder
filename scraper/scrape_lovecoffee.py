# -*- coding: utf-8 -*-
"""
scrape_lovecoffee.py

らぶこーひー自家焙煎豆店(lovecoffeejikabaisen.com、北海道札幌市、
自家焙煎豆のオンライン販売)の商品情報を取得する。WooCommerce(Store API)。

【店舗発見の経緯】
2026-09-16の北海道エリア調査で一度候補に上がったが、WooCommerce Store API
がGitHub Actions実行時のみ403 Forbiddenを返す(ローカルcurlでは同時刻に
200 OK)ことを確認して見送っていた店舗。全国再調査でこの制約を再確認した
ところ、ローカル開発環境からのAPIアクセスは問題無く行えることを確認できた
ため実装対象に追加した(GitHub Actionsの週次自動再スクレイピングは今後
失敗する可能性があるが、aggregate_shops.py側は該当データファイルが
見つからない場合に既存データを保持する仕様のため、実害は無い)。

【対象商品について】
実データ確認済み(Store API `/wp-json/wc/store/v1/products?per_page=100`
全46件、2026-09時点): 商品名に「【¥N／100g】」という単価表記を持つ
コーヒー豆17件(ストレート12・ブレンド5、うち「ペンギンブレンド
アイスコーヒー」は名称にアイスコーヒーを含むが実体は焙煎豆そのものの
販売[水出し用ブレンドとして焙煎されているだけ]のため対象に含める)を
対象とする。お試しセット・定期便「たのしくる」・ドリップバッグ単品
(スペシャリティドリップバッグ14g入り)・水出しコーヒーパック(既成の
コールドブリューパック、生豆ではなく抽出済み想定の加工品)・自家焙煎
ナッツ類・バナナチップ・ギフトセット(複数銘柄セット)・グッズ/アパレル
(マグ・Tシャツ・パーカー等)は対象外。

【価格の取得方法について】
実データ確認済み: 対象商品はいずれもWooCommerceの「variable」型商品で、
「豆の状態」という選択属性(豆のまま/各種挽き方/ドリップバッグ/水出し
パック等)ごとに価格が異なる。トップレベルのprices.priceは最安値の
バリエーション(ドリップバッグや水出しパック等)の価格を返すため、
商品名に明記された「100g」相当の価格とは異なる(例: 商品名の価格と
一致しないケースを実データで確認済み)。「豆のまま」(属性値スラッグ
category01)のバリエーションを明示的に選んで価格を取得する必要がある。

【商品説明の構造について】
実データ確認済み: 商品ページに`dl.c-detail-data > div.c-detail-data__row`
というアコーディオン構造があり、`dt.c-detail-data__ttl`(見出し)と
`dd.c-detail-data__desc`(内容)のペアが「商品説明」(産地ストーリー・
テイスティング文、★評価行を含む)→「らぶこーひーの仕事」(全商品共通の
焙煎工程の一般論、商品固有情報が無いため除外)→「商品情報」(●特徴/
●生産者/●品種/●認証/●サイズ/●規格/●標高/●精製/●乾燥/●栽培、または
ブレンドの場合●特徴/●ブレンド内容/●生産地)→「定期便はこちら」
(クロスセル、除外)の順で並ぶ。「商品説明」から★評価行を除いたテキストを
flavor_notesに、「商品情報」の●生産者/●品種/●標高/●精製/●規格(ストレート)
または●ブレンド内容/●生産地(ブレンド)をfarm_noteに採用する。

【デカフェの除去方法について】
実データ確認済み: 商品名(raw_name)自体には除去方法名の言及が無く、
「マウンテンウォーター(製)法」という記載は本文(商品説明)側にのみ
現れる。aggregate_shops.py側のinfer_decaf_process()は商品名のみを見る
ため、この店舗のデカフェ3商品では検出できず「デカフェ(除去方法の
詳細記載なし)」という曖昧な値になってしまう。本文にマウンテンウォーター
系の言及がある場合はスクレイパー側でdecaf_processを明示的に設定する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "らぶこーひー自家焙煎豆店",
    "url": "https://lovecoffeejikabaisen.com/",
    "platform": "WooCommerce",
    "address": "北海道札幌市",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(WooCommerce標準構成を想定)",
}

BASE_URL = "https://lovecoffeejikabaisen.com"
API_URL = f"{BASE_URL}/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

# 商品名に「【¥N／100g】」表記を持つ豆単品のみを対象とする(お試しセット・
# 定期便・ドリップバッグ単品・水出しパック・フード・ギフト・グッズは除外)。
TARGET_PRODUCT_IDS = [
    9773, 9787, 9358, 9812, 4050, 3913, 4061, 4088,
    9959, 4140, 6329, 4148, 9992, 8548, 9351, 4181, 6999,
]

STAR_PATTERN = re.compile(r"[★☆]")
DECAF_PATTERN = re.compile(r"マウンテンウォーター|マウンテン・ウォーター")
BLEND_LABELS = ("ブレンド内容", "生産地")
STRAIGHT_LABELS = ("生産者", "品種", "標高", "精製", "規格")
LABEL_PATTERN = re.compile(r"^●(.+)$")


def fetch_products() -> dict[int, dict]:
    resp = requests.get(API_URL, headers=REQUEST_HEADERS, params={"per_page": 100}, timeout=20)
    return {p["id"]: p for p in resp.json()}


def fetch_bean_price(product: dict) -> int | None:
    variation_id = None
    for v in product.get("variations", []):
        if any(a.get("value") == "category01" for a in v.get("attributes", [])):
            variation_id = v["id"]
            break
    if variation_id is None:
        return None
    resp = requests.get(f"{API_URL}/{variation_id}", headers=REQUEST_HEADERS, timeout=20)
    price = resp.json().get("prices", {}).get("price")
    return int(price) if price is not None else None


def fetch_detail_rows(pid: int) -> dict[str, list[str]]:
    resp = requests.get(f"{BASE_URL}/product/{pid}/", headers=REQUEST_HEADERS, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = {}
    for row in soup.select("dl.c-detail-data > div.c-detail-data__row"):
        ttl_el = row.select_one(".c-detail-data__ttl")
        desc_el = row.select_one(".c-detail-data__desc")
        if not ttl_el or not desc_el:
            continue
        ttl = ttl_el.get_text(strip=True)
        lines = [l.strip() for l in desc_el.get_text("\n", strip=True).split("\n") if l.strip()]
        rows[ttl] = lines
    return rows


def parse_flavor_notes(rows: dict[str, list[str]]) -> str | None:
    lines = rows.get("商品説明", [])
    kept = [l for l in lines if not STAR_PATTERN.search(l)]
    return "\n".join(kept) or None


def parse_farm_note(rows: dict[str, list[str]], is_blend: bool) -> tuple[str | None, dict]:
    lines = rows.get("商品情報", [])
    labels: dict[str, str] = {}
    current_key = None
    for line in lines:
        m = LABEL_PATTERN.match(line)
        if m:
            current_key = m.group(1).strip()
            labels[current_key] = ""
            continue
        if current_key:
            labels[current_key] = (labels[current_key] + " " + line).strip() if labels[current_key] else line

    wanted = BLEND_LABELS if is_blend else STRAIGHT_LABELS
    parts = [f"{k}: {labels[k]}" for k in wanted if labels.get(k)]
    farm_note = "、".join(parts) if parts else None
    return farm_note, labels


def build_record(pid: int, product: dict) -> dict | None:
    title = product["name"].strip()
    price = fetch_bean_price(product)
    if price is None:
        print(f"[warn] 100g豆のまま価格が見つからないためスキップ: pid={pid} ({title})")
        return None

    rows = fetch_detail_rows(pid)
    parsed = parse_product(title)
    url = f"{BASE_URL}/product/{pid}/"

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
    flavor_notes = parse_flavor_notes(rows)
    farm_note, labels = parse_farm_note(rows, is_blend)

    origin_note = labels.get("生産者") or labels.get("生産地")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精製"):
        parsed["processing_method"] = normalize_processing_method(labels["精製"])

    variety = labels.get("品種")
    stock_status = detect_stock_status(title)

    decaf_process = None
    if ("デカフェ" in title or "カフェインレス" in title) and DECAF_PATTERN.search(flavor_notes or ""):
        decaf_process = "マウンテンウォータープロセスによりカフェインを除去"

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
        "decaf_process": decaf_process,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    records = []
    flavored_records = []
    for pid in TARGET_PRODUCT_IDS:
        product = products.get(pid)
        if product is None:
            print(f"[warn] 商品が見つかりません: pid={pid}")
            continue
        try:
            detail = build_record(pid, product)
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
    with open("data_lovecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lovecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
