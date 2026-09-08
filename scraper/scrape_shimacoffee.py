# -*- coding: utf-8 -*-
"""
scrape_shimacoffee.py

島珈琲(しまこーひー、shima-coffee.com、大阪府豊中市岡町南1丁目5番47号
〈岡町本店・自家焙煎の拠点〉、自家焙煎豆のオンライン販売)の商品情報を
取得する。WordPress+Welcart(usces-cart、旧称USCES)。ドメインは
https://shima-coffee.com/ から https://www.shima-coffee.com/ へ301
リダイレクトされる。

住所は自社サイトの岡町本店紹介ページ(https://www.shima-coffee.com/
shopinfo/okamachi/ 、「島珈琲（しまこーひー） 〒561-0883 豊中市岡町南
1丁目5番47号」)で確認済み。同ページの店主プロフィールに「帰国後　すぐに
島珈琲を開店。２００２年のことでした」「10年目の節目で高槻店を出店する
ことができました」とあり、岡町本店が自家焙煎の創業拠点・高槻店は後年の
2号店であるため岡町本店の住所を採用する。

robots.txt確認済み(2026-09時点): WordPress標準robots.txt(/wp-admin/のみ
Disallow、admin-ajax.phpはAllow)で実質許可。

【商品一覧の取得方法について】
実データ確認済み: 商品ページはブレンド(ble-0001〜0010、10件)・深焙煎
シングルオリジン(drs-0001〜0005、5件)・スコットブレンド(exma-0001、1件)・
中焙煎シングルオリジン(mrs-0001〜0005、5件)のURLパターンで構成される
(商品一覧カテゴリページ/item/itemgenre/{blend,deep-roast,exma,kaori,
medium-roast,quick-coffee,gift}/を巡回して実データ確認済み)。

【非コーヒー豆商品の除外について】
実データ確認済み: 「ドリップバッグ　クラシックマイルド5p」等のqck-〜
シリーズ(9件、ドリップバッグ単品)、「ドリップバッグ 40pギフトセット」
等のgft-〜シリーズ(11件、ギフトセット)、「香りあふれる便（1回のみ）」
等のkaori-〜シリーズ(2件、複数銘柄を組み合わせた定期便お試しセットで
挽き方セレクタが2個あることから2銘柄の詰め合わせと確認済み)が非対象の
ため、そもそもURLリストに含めず巡回対象外とする。

【重量・価格・在庫状況の取得方法について】
実データ確認済み: 各商品ページにはWelcartのSKUフォームブロック
(`<div class="skuname">100g</div>` 等)が重量ごとに複数個埋め込まれて
おり、直後の`field_cprice`要素に税込価格、`zaikostatus`要素に「在庫状態 :
在庫有り」等の在庫文言がある。ble系は100g/200g/300g/400g/500gの5サイズ、
exma-0001のみ「250gパック × 2」という単一バリアント(合計500g)。
最小重量のSKUブロックを代表として採用する(exma-0001は250g×2で合計500g
のみのため、その合計値を採用)。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "島珈琲",
    "url": "https://www.shima-coffee.com/",
    "platform": "WordPress(Welcart/usces-cart)",
    "address": "大阪府豊中市岡町南1丁目5番47号",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。WordPress標準robots.txt、"
                          "/wp-admin/のみDisallow)",
}

BASE_URL = "https://www.shima-coffee.com"
PRODUCT_SLUGS = (
    [f"ble-{i:04d}" for i in range(1, 11)]
    + [f"drs-{i:04d}" for i in range(1, 6)]
    + ["exma-0001"]
    + [f"mrs-{i:04d}" for i in range(1, 6)]
)
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

SKU_BLOCK_PATTERN = re.compile(
    r'<div class="skuname">([^<]*)</div>.*?zaikostatus">([^<]*)</div>'
    r'.*?field_cprice">\s*¥?\s*([\d,]+)\s*</span>',
    re.DOTALL,
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
MULTIPLIER_PATTERN = re.compile(r"[×xX]\s*(\d+)")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_title(html: str) -> str | None:
    m = re.search(r'property="og:title" content="([^"]*)"', html)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()


def extract_sku_blocks(html: str) -> list[dict]:
    blocks = []
    for weight_label, stock_text, price_raw in SKU_BLOCK_PATTERN.findall(html):
        wm = WEIGHT_PATTERN.search(weight_label)
        if not wm:
            continue
        weight_g = int(wm.group(1))
        mm = MULTIPLIER_PATTERN.search(weight_label)
        if mm:
            weight_g *= int(mm.group(1))
        price = int(price_raw.replace(",", ""))
        in_stock = "有り" in stock_text
        blocks.append({"weight_g": weight_g, "price": price, "in_stock": in_stock})
    return blocks


def build_record(slug: str) -> dict | None:
    url = f"{BASE_URL}/{slug}/"
    try:
        html = fetch_html(url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
        return None

    title = extract_title(html)
    if not title:
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": url,
        }

    blocks = extract_sku_blocks(html)
    canonical = min(blocks, key=lambda b: b["weight_g"]) if blocks else None
    price = canonical["price"] if canonical else None
    weight_g = canonical["weight_g"] if canonical else None
    structural_out_of_stock = bool(blocks) and not any(b["in_stock"] for b in blocks)

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for slug in PRODUCT_SLUGS:
        detail = build_record(slug)
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
    with open("data_shimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shimacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
