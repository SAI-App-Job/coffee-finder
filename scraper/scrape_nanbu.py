# -*- coding: utf-8 -*-
"""
scrape_nanbu.py

南部珈琲 ナンブコーヒー(shop.nanbu-coffee.com、茨城県牛久市栄町、
自家焙煎豆のオンライン販売。エスカード牛久店を含む2拠点)の商品情報を
取得する。BASE(白ラベルドメイン)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全93件): 同一銘柄が「(焙煎豆200g)」(焙煎済み)と
「(生豆500g)」(自家焙煎希望者向けの生豆、焙煎済みではない)の2形態で
別商品登録されており、「生豆」表記の商品は焙煎済みコーヒー豆単品では
ないため除外する(「焙煎豆」側のみを対象とする)。またアニメコラボ
グッズ(アクリルスタンド)・ハリオ製品(コールドブリューピッチャー・
コーヒーボトル)・各種ギフトセット・ドリップコーヒーバッグ・
オリジナルアイスコーヒー(液体)・コーヒー自家焙煎セット(生豆キット)・
カリタ クリーニングブラシ・bonmac コーヒーミル(器具)・安曇野の天然水
(ボトル水)・詰め合わせギフト専用箱(箱のみ)・初回限定お試しセットが
コーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。

【flavor_notes/farm_note(テイスティングノート・農園情報)について
(2026-09-20追記)】
実データ確認済み: og:descriptionを一切読んでいなかった。全商品共通で
「(今月のお買い得豆の場合のみ)今月のお買い得豆通常200g 1960円→
1660円」のような月替わり特売の価格差分表記に続けて風味を説明する自由
記述文があり、その後「分量：生豆 240g → 焼き上がり 200g販売単位：...」
という注意書きが必ず続く(全商品共通、句読点無しで連結されていることが
多い)。単一原産地商品にはこの間に「生産地：」「産地：」「生産者：」
「地域：」「標高：」「品種：」「規格：」等のラベルが入るが、店舗・
商品によって表記(「生産地」/「産地」)や順序(「生産者」が最初に来る
場合もある)が揺れる。ブレンド商品にはラベルが一切無い。
「分量：」を本文全体の終端とし、その中で上記ラベルのいずれかが最初に
現れた位置をflavor_notesの終端とする(ラベルが無ければ「分量：」までの
全文をflavor_notesとする)。「生産地：」「産地：」「地域：」の値
(次のラベルまたは「分量：」の直前まで)はfarm_note用のregion_detailに
反映する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "南部珈琲",
    "url": "https://shop.nanbu-coffee.com/",
    "platform": "BASE",
    "address": "茨城県牛久市栄町1-21",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.nanbu-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "生豆", "ギフトセット", "ドリップコーヒーバッグ", "アイスコーヒー",
    "自家焙煎セット", "クリーニングブラシ", "COFFEE MILL", "天然水",
    "箱のみ", "お試しセット", "アクリルスタンド", "ピッチャー", "ボトル",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PROMO_PREFIX_PATTERN = re.compile(r"^今月のお買い得豆[^→]*→\s*[\d,]+円")
QUANTITY_MARKER_PATTERN = re.compile(r"分量[：:]")
LABEL_NAMES = "生産地|産地|生産者|地域|標高|品種|規格|精選方法"
FLAVOR_BOUNDARY_PATTERN = re.compile(r"(生産地|産地|生産者|地域|標高|品種)[：:]")
REGION_VALUE_PATTERN = re.compile(rf"(生産地|産地|地域)[：:]\s*(.+?)(?={LABEL_NAMES}|分量|$)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_and_region(description: str | None) -> tuple[str | None, str | None]:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None, None
    text = PROMO_PREFIX_PATTERN.sub("", description)
    qty_m = QUANTITY_MARKER_PATTERN.search(text)
    content = text[:qty_m.start()] if qty_m else text

    boundary_m = FLAVOR_BOUNDARY_PATTERN.search(content)
    flavor_notes = (content[:boundary_m.start()] if boundary_m else content).strip() or None

    region_m = REGION_VALUE_PATTERN.search(content)
    region_detail = region_m.group(2).strip() if region_m else None
    return flavor_notes, region_detail


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes, region_detail = extract_flavor_and_region(desc_el["content"] if desc_el else None)
    return {"title": title, "price": price, "flavor_notes": flavor_notes, "region_detail": region_detail}


def build_record(product_url: str, fields: dict) -> dict | None:
    title = fields["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": fields["price"],
            "product_url": product_url,
        }

    stock_status = detect_stock_status(title)
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
        "region_detail": fields.get("region_detail"),
        "flavor_notes": fields.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": fields["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    fields = extract_og_fields(fetch_page(url))
    if not fields:
        return None
    return build_record(url, fields)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue
        if any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record(product_url, fields)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        import json
        with open("data_nanbu.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_nanbu.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
