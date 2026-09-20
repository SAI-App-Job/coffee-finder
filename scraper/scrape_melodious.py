# -*- coding: utf-8 -*-
"""
scrape_melodious.py

自家焙煎メロディアスコーヒー(melodious.base.ec、東京都足立区保木間、
就労継続支援B型事業所メロディー竹の塚が運営)の商品情報を取得する。
BASEの白ラベルドメイン「.base.ec」。情報サイト(melodiouscoffee.jp、
静的HTML)とは別にこちらが実際のオンラインショップ。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上26件): 「水出しアイスコーヒー デルパック」
(液体)がコーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。残りは
ブレンド2種+ストレート数種(100g/200g)で、デカフェも含む。

【flavor_notes・farm_note(2026-09-20追記)】
実データ確認済み: og:descriptionの内容が商品タイプによって2系統に分かれる。
(1)ブレンド・ドリップバッグ商品は「■商品説明<テイスティング文>■商品詳細
<品名/原材料/内容量等の事務的スペック>」の構成で、「■商品説明」の直後
から次の「■」見出しの直前までが実際のテイスティング文になっている
(採用しflavor_notesとする)。(2)ストレート単一原産地商品(デカフェ含む)は
「■商品説明」見出しが無く、代わりに「生産地：」「生産地域：」「標高：」
「品種：」等のラベル付きスペック情報のみが連結されている(テイスティング
文は無い)。これをflavor_notesとして採用すると事務的スペックを「テイス
ティングノート」と誤表示することになるため採用せず、代わりにfarm_note用の
断片フィールド(farm_name/region_detail/altitude_note/variety_note)として
取得する(「生産地」の値が「農園」を含む場合はfarm_name、それ以外は
region_detailとして扱う。「生産地域」が別途あれば優先してregion_detailに
採用)。上記いずれの構造にも当たらない場合(例: デカフェのドリップバッグ
商品は見出し無しの自由記述のみ)は、説明文全体をそのままflavor_notesとして
採用する(フォールバック)。og:descriptionが空の商品(1件、マンデリンG1
深煎り無印)はflavor_notes・farm_noteともに取得できない。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎メロディアスコーヒー",
    "url": "https://melodious.base.ec/",
    "platform": "BASE",
    "address": "東京都足立区保木間1-1-13 足立水道会館2階",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://melodious.base.ec"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

FLAVOR_DESC_PATTERN = re.compile(r"■\s*商品説明\s*(.*?)(?=■|$)", re.DOTALL)
FARM_LABEL_PATTERN = re.compile(r"(生産地域|生産地|輸出業者|標高|精選|品種|焙煎度|SCA評価)[：:]+\s*")


def extract_flavor_notes_and_farm(description: str | None) -> dict:
    """理由はモジュールdocstring参照。"""
    empty = {"flavor_notes": None, "farm_name": None, "region_detail": None,
              "altitude_note": None, "variety_note": None}
    if not description:
        return empty

    m = FLAVOR_DESC_PATTERN.search(description)
    if m:
        text = m.group(1).strip()
        return {**empty, "flavor_notes": text or None}

    matches = list(FARM_LABEL_PATTERN.finditer(description))
    if matches:
        values = {}
        for i, lm in enumerate(matches):
            start = lm.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
            value = description[start:end].strip()
            if value:
                values[lm.group(1)] = value

        farm_name = None
        region_detail = None
        place = values.get("生産地")
        if place and "農園" in place:
            farm_name = place
        elif place:
            region_detail = place
        if values.get("生産地域"):
            region_detail = values["生産地域"]

        return {
            "flavor_notes": None,
            "farm_name": farm_name,
            "region_detail": region_detail,
            "altitude_note": values.get("標高"),
            "variety_note": values.get("品種"),
        }

    return {**empty, "flavor_notes": description.strip() or None}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    description = desc_el["content"] if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "description": description}


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
    flavor_and_farm = extract_flavor_notes_and_farm(fields.get("description"))

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
        "flavor_notes": flavor_and_farm["flavor_notes"],
        "farm_name": flavor_and_farm["farm_name"],
        "region_detail": flavor_and_farm["region_detail"],
        "altitude_note": flavor_and_farm["altitude_note"],
        "variety_note": flavor_and_farm["variety_note"],
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
        with open("data_melodious.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_melodious.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
