# -*- coding: utf-8 -*-
"""
scrape_sukocoffee.py

寿古珈琲(Suko Coffee、suko.ocnk.net、〒856-0801 長崎県大村市寿古町813-1、
長崎スコーコーヒーパーク直営のオンラインショップ)の商品情報を取得する。
おちゃのこネット(Ocnk)。

【住所について】
公式サイトの店舗情報ページ(https://suko.ocnk.net/info、有限会社中島
珈琲本社)で「〒856-0801 長崎県大村市寿古町813-1」を確認済み
(2026-09時点)。

robots.txt確認済み(2026-09時点): 他のOcnk系店舗と同様、GPTBot等AI系
ボットのみ個別にDisallow、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに列挙された`/product/N`形式のURL、
全13件を対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み(全13件): 「寿古の珈琲キャンディー」(菓子)・
「寿古のおてがるコーヒードリップ」各種パック(ドリップバッグ)・
「アミーガーさんが選んだ寿古のインスタント珈琲」(インスタント)・
「寿古珈琲の果実ジャム」(ジャム)・「寿古の水出しアイスコーヒー」
(ボトル飲料)が非対象。NON_BEAN_KEYWORDSで除外すると、焙煎豆商品は
「寿古珈琲 S-15」(豆190g/粉200gの2形態)・「寿古珈琲 S-10」(粉200gのみ、
豆形態のSKUが見つからず)・「オリジナルブレンドコーヒー」(豆500g/
粉500gの2形態)の3銘柄のみが残る。

【豆/粉の重複について】
実データ確認済み: 同一銘柄が「豆」「粉」の挽き方違いで別商品登録されて
いる場合、「豆のまま」を優先して代表採用する(S-10のように豆形態が
存在しない銘柄はそのまま粉形態を採用する)。

【flavor_notes(2026-09-22追記)】
実データ確認済み: 商品詳細ページのdiv.item_desc_textに対象3件全てで
テイスティング文・生豆生産国・内容量・焙煎度等が入っている。末尾に
全件共通で「※20個以上ご購入される場合は、お手数ですが当店にお電話を
いただき、...電話：0957-55-4850」という大量購入時の案内が続くため、
この直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "寿古珈琲",
    "url": "https://suko.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "長崎県大村市寿古町813-1",
    "prefecture": "長崎県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://suko.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["キャンディー", "ドリップ", "インスタント", "ジャム", "水出し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
BASE_NAME_STRIP_PATTERN = re.compile(r"[【\[]\s*(豆|粉)\s*\d+\s*[gｇ]\s*[】\]]")
FLAVOR_STOP_PATTERN = re.compile(r"※20個以上ご購入される場合は")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one("title")
    if not title_el:
        return None
    raw_title = title_el.get_text(strip=True).split("｜")[0].strip()
    # ページタイトルは「店名｜商品名｜カテゴリ」の順序が店舗により異なるため、
    # 「長崎スコーコーヒーパーク」を含む区切りは除外して商品名らしき部分を拾う
    parts = [p.strip() for p in title_el.get_text(strip=True).split("｜") if p.strip() and "長崎スコーコーヒーパーク" not in p]
    title = parts[0] if parts else raw_title
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one("div.item_desc_text")
    flavor_notes = desc_el.get_text("\n", strip=True) if desc_el else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = BASE_NAME_STRIP_PATTERN.sub("", item["title"]).strip()
        is_whole_bean = "豆" in item["title"]
        existing = by_base_name.get(base_name)
        if existing is None or (is_whole_bean and "豆" not in existing["title"]):
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields or any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({
            "title": fields["title"],
            "price": fields["price"],
            "url": product_url,
            "flavor_notes": fields.get("flavor_notes"),
        })

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
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
    with open("data_sukocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sukocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
