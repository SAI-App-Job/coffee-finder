# -*- coding: utf-8 -*-
"""
scrape_chanpulucoffee.py

チャンプルーコーヒー(chanpulu.base.shop、沖縄県石垣市石垣13 玉城ビル1F)の
商品情報を取得する。BASE(白ラベルドメイン)。

【住所について】
特定商取引法ページ(https://chanpulu.base.shop/law)で実際に確認したところ
「事業者の名称: 村田信二 / 事業者の所在地: 〒907-0023 沖縄県石垣市石垣13
玉城ビル1F」であることを確認した(2026-09時点)。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品について】
実データ確認済み(全5件): 「チャンプルーコーヒー焙煎豆　100g」のみが対象。
ld+jsonの説明文で「世界各地の高級コーヒー豆と石垣島産コーヒー豆をチャンプルー
(ブレンド)」と明記されている(石垣島産の豆を含む自家焙煎ブレンド)。
「チャンプルー」は沖縄方言で「混ぜる」を意味し、この店舗名・商品名自体が
ブレンドを表す独自の呼称のため、coffee_parserの標準BLEND_KEYWORDS
(「ブレンド」「blend」「ミックス」)では検出できない。この店舗限定で
「チャンプルー」を含む場合はcategory="ブレンド"にローカルで補正する。
説明文には「さわやかチャンプルー」(浅煎り寄り)・「深煎りチャンプルー」の
2種の焙煎違いが選べると記載されているが、詳細ページの静的HTMLからは
バリアント別の個別価格を構造的に取得できなかった(実データ確認済み。BASEの
variantsデータがこの店舗ではld+json/OGP/静的HTMLのいずれにも現れない)ため、
1商品(デフォルト価格980円)として記録する。

【非コーヒー豆商品の除外について】
実データ確認済み(全5件): ドリップパック(12g単品・10個入セット)・
オリジナルマグカップ・オリジナルステッカーがNON_BEAN_KEYWORDSで除外される。

【flavor_notes(2026-09-22追記)】
実データ確認済み: ld+jsonのdescriptionに紹介文と2種の焙煎違い
(さわやかチャンプルー/深煎りチャンプルー)それぞれのテイスティング文、
「【100gのこだわり】」の鮮度についての説明が入っている。末尾に「豆を
挽いてお送りすることも出来ます。種類のところで選択してください。」と
いう挽き方選択案内〜「※送料のご案内」の発送方法案内が続くため、この
直前で打ち切る。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "チャンプルーコーヒー",
    "url": "https://chanpulu.base.shop/",
    "platform": "BASE",
    "address": "沖縄県石垣市石垣13 玉城ビル1F",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://chanpulu.base.shop"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["ドリップパック", "マグカップ", "ステッカー"]

LD_JSON_PATTERN = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"豆を挽いてお送りすることも出来ます")


def fetch_sitemap_urls() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return [u for u in re.findall(r"<loc>([^<]+)</loc>", resp.text) if "/items/" in u]


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


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
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

    # 理由はdocstring参照:「チャンプルー」はこの店舗独自のブレンドを表す呼称
    if "チャンプルー" in title and parsed["category"] != "ブレンド":
        parsed["category"] = "ブレンド"

    stock_status = detect_stock_status(title, item.get("out_of_stock", False))
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for url in urls:
        try:
            data = fetch_ld_json(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not data:
            continue

        title = (data.get("name") or "").strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            time.sleep(CRAWL_DELAY_SECONDS)
            continue

        prev = previous.get(url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            time.sleep(CRAWL_DELAY_SECONDS)
            continue

        offers = data.get("offers") or {}
        price = int(float(offers["price"])) if offers.get("price") is not None else None
        out_of_stock = offers.get("availability") not in (
            "http://schema.org/InStock", "https://schema.org/InStock",
        )

        flavor_notes = (data.get("description") or "").strip()
        fm = FLAVOR_STOP_PATTERN.search(flavor_notes)
        if fm:
            flavor_notes = flavor_notes[:fm.start()].strip()

        detail = build_record({
            "raw_name": title, "price": price, "out_of_stock": out_of_stock, "product_url": url,
            "flavor_notes": flavor_notes or None,
        })
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_chanpulucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chanpulucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
