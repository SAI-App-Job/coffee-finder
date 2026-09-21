# -*- coding: utf-8 -*-
"""
scrape_aicoffee.py

ai珈琲(aicoffee.thebase.in、広島県東広島市西条中央4丁目10-43 フロンティア
相沢、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【住所について】
BASEストアの特定商取引法ページ(https://aicoffee.thebase.in/law)には
BASE株式会社自体の住所(東京都港区六本木)しか記載されていなかったが、
公式サイト(https://aicoffee.jp/shop/)に実店舗の住所が別途明記されており、
候補リストの住所と一致することを実データ確認した(2026-09時点)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【商品構成について】
実データ確認済み(sitemap.xml全23件、2026-09-21再確認時点25件): コーヒー
豆単品8銘柄(【ゲイシャ】フアン ホセPeru・【ほろ苦】季節のブレンド・
【すっきり】キイロのトッポBlend・【すっきり】ロジャー ウレニャCosta
Rica・【ほろ苦】プーノPeru・【ほろ苦】リオブリジャンテ農園Brazil、
2026-09-21再確認時点で新たに追加された【ほろ苦】モカEthiopia・
【フルーティー】Addisu Kidane Ethiopiaを含む)と、非対象の「選べる
コスパコーヒー」(複数銘柄から選ぶ福袋的商品)、「季節のおすすめ/ほろ苦/
すっきり・フルーティーなコーヒー ◯種セット」各種(複数銘柄詰め合わせ)、
扇形・円錐・ウェーブ各種コーヒーフィルター(器具)。NON_BEAN_KEYWORDSで
除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象8件全てで香り/フルーティー/甘み/
ボディ/苦味の記号評価+「どんな人どんな時におすすめ？」+「ペーパー
ドリップでのおすすめ抽出」+産地紹介・テイスティング文+産地スペック
(生産地/標高/品種/精製方法/入港時期/焙煎度)が入っている。末尾に
「焙煎度：<値>」の直後から重量ごとの価格一覧(例:「100g￥1500200g
￥3000」)が区切り無く続くため、最初の「<数字>g￥<数字>」パターンの
直前で打ち切る。

【価格・重量の取得方法について】
実データ確認済み: 各商品は「豆のまま/中挽き/粗挽き」の挽き方セレクトとは
別に、重量セレクト(例:「50g￥1500」「100g　￥1500＋　¥1,400」「200g
￥1500＋　¥3,500」)を持つ。最小重量(50g)が追加料金無しの基準価格であり、
OGPのproduct:price:amountメタタグの値と一致することを実データ確認した
ため、これを採用する。重量はセレクトの中から最小のg数を抽出する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ai珈琲",
    "url": "https://aicoffee.thebase.in/",
    "platform": "BASE",
    "address": "広島県東広島市西条中央4丁目10-43 フロンティア相沢",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://aicoffee.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "フィルター", "選べる"]
WEIGHT_OPTION_PATTERN = re.compile(r">\s*(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"\d+g￥[\d,]+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup, html: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    weight_matches = [int(m.group(1)) for m in WEIGHT_OPTION_PATTERN.finditer(html)]
    weight_g = min(weight_matches) if weight_matches else None

    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()

    return {"title": title, "price": price, "weight_g": weight_g, "flavor_notes": flavor_notes or None}


def build_record(item: dict) -> dict | None:
    title = item["title"].strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        fields = extract_fields(soup, resp.text)
        if not fields:
            continue
        all_items.append({**fields, "url": product_url})

    records = []
    flavored_records = []
    for item in all_items:
        detail = build_record(item)
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
    with open("data_aicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_aicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
