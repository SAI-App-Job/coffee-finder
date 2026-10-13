# -*- coding: utf-8 -*-
"""
scrape_yamadacoffeeamami.py

山田珈琲 Amami Island(https://amamiycoffee.theshop.jp/、公式 https://yamadacoffee.net/、
鹿児島県奄美市笠利町和野364-3)の自家焙煎コーヒー豆の商品情報を取得する。BASE。
(scrape_yamadacoffee.py は岐阜県の別店舗「山田珈琲」のため別名にしている)

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

【住所について】
BASEの特商法ページ(/law)に事業者の所在地として「〒894-0503 鹿児島県奄美市笠利町和野364-3」
(事業者名: 山田拓郎)が記載されている(2026-10-13確認)。

【対象商品について】
sitemap.xml の商品24件のうち、200g のコーヒー豆7銘柄(あまみブレンド+シングルオリジン6種)を
対象とする。「きびおれ」(カフェオレベース)・ギフトセット・コーヒーバッグ・メール便セット
(180g×2P)・雑貨(手ぬぐい等)は除外。各銘柄とも200gのみの1ページ構成。
商品名はタイトルの全角スペースと重量表記「200g」を除いたもの。
価格・在庫(item_purchasability)・説明は商品ページから取得し、説明文末尾の
<国><エリア><農園名><品種><生産処理><焙煎度合> の表記から産地等を取る。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests等は個別にDisallow、User-agent: *では許可)。
識別可能な独自User-Agentを使用する。
"""

import html as _html
import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "山田珈琲 Amami Island",
    "url": "https://amamiycoffee.theshop.jp/",
    "platform": "BASE",
    "address": "鹿児島県奄美市笠利町和野364-3",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://amamiycoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 分類の上書き(Noneなら自動判定))
ITEMS = [
    ("3434488", "ブレンド"),   # あまみブレンド
    ("161129091", None),      # ケニア ングルエリAB
    ("119323709", None),      # エチオピア カルマチ カーボニックマセレーション・ナチュラル
    ("3404361", None),        # ブラジル パッセイオ イエローブルボン
    ("152847729", None),      # インドネシア マンデリン ブルーリントン
    ("3404569", None),        # グアテマラ ラ・タシータ
    ("3404072", None),        # コロンビア アンデスコンドル
]

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORDS = [("ライト", "ライトロースト"), ("シナモン", "シナモンロースト"), ("ミディアム", "ミディアムロースト"),
               ("ハイ", "ハイロースト"), ("フルシティ", "フルシティロースト"), ("シティ", "シティロースト"),
               ("フレンチ", "フレンチロースト"), ("イタリアン", "イタリアンロースト")]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def tag(desc: str, key: str):
    m = re.search(r"<" + key + r">\s*([^<]*)", desc)
    return clean(m.group(1)) if m else None


def build_record(item_id: str, category_override: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    t = resp.text
    title = clean(_html.unescape(TITLE_PATTERN.search(t).group(1)))
    title = re.sub(r"\s*\|.*$", "", title)
    name = clean(re.sub(r"\s*200\s*g\s*$", "", title, flags=re.IGNORECASE))
    desc = _html.unescape(DESC_PATTERN.search(t).group(1)) if DESC_PATTERN.search(t) else ""
    price_m = PRICE_PATTERN.search(t)
    pm = PURCHASABILITY_PATTERN.search(t)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    country_label = tag(desc, "国")
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        c = detect_country_name(country_label) if country_label else None
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "product_description"
        elif not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        proc = tag(desc, "生産処理")
        if proc and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(proc)
        parsed = apply_category_hint_fallback(parsed, name)

    roast_label = tag(desc, "焙煎度合")
    roast_level = None
    if roast_label and "&" not in roast_label:
        for kw, lv in ROAST_WORDS:
            if roast_label.startswith(kw):
                roast_level = lv
                break
    farm_parts = []
    for key, label in (("エリア", "エリア"), ("農園名", "農園"), ("生産者", "生産者"), ("品種", "品種")):
        v = tag(desc, key)
        if v:
            farm_parts.append(f"{label}: {v}")
    # 説明文の本文(<国>以前)をテイスティング・説明として保持
    body = clean(desc.split("<国>")[0].split("<内容量>")[0])[:400] or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_label,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": body,
        "blend_components": [],
        "decaf_process": None,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": 200,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, cat in ITEMS:
        try:
            rec = build_record(item_id, cat)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if rec:
            records.append(rec)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yamadacoffeeamami.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamadacoffeeamami.json に出力しました")


if __name__ == "__main__":
    main()
