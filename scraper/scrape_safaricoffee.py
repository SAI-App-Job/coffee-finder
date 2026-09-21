# -*- coding: utf-8 -*-
"""
scrape_safaricoffee.py

SAFARI COFFEE ROASTER(safaricoffee.theshop.jp、〒870-0856 大分県大分市畑中
3丁目2番7号コーポ森101、自家焙煎豆のオンライン販売)の商品情報を取得する。
theShop(BASE系列のtheshop.jpドメイン)。

【住所について】
特定商取引法ページ(https://safaricoffee.theshop.jp/law)で実データ確認済み
(2026-09時点): 事業者の名称「秋吉真吾」、事業者の所在地「〒870-0856
大分県大分市畑中３丁目２番７号コーポ森１０１」との記載を確認。候補リストの
住所(登録上の住所であり実店舗ではない可能性があるが、本プロジェクトの
既存方針により特定商取引法ページの住所をそのまま採用する)と一致。

robots.txt確認済み(2026-09時点): 他のBASE/theShop系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(全22件): sitemap.xmlの/items/配下22件のうち、商品名末尾に
「(NNNg)」の重量表記がある単一銘柄・ブレンドの焙煎豆は7件(Honduras
Kukurucho Geisha・Mexico Santuario Project・Kenya Nyeri Tegu・Burundi
Kayave・Ethiopia Bench Maji・【Decaf】Ethiopia Sidamo・Assemblage Blend)。
「【大分店10周年記念】Anniversary Selection Mexico×Honduras 80g×2種」は
2銘柄詰め合わせセットのため非対象。他はCOLD BREW水出しパック・
Subscription定期購入・Latte Base(カフェラテ用リキッド)・Drip Bag Gift・
Whole Sale(卸売問い合わせ用のダミー商品)のため非対象。NON_BEAN_KEYWORDSで
除外する。

【flavor_notes実装時(2026-09-21)の再確認について】
実データ確認済み: 「Mexico Santuario Project」は単品としては取り扱い
終了となっており、「【大分店10周年記念】Anniversary Selection Mexico
Santuario Project×Honduras Kukurucho Geisha 80g×2種」(既存の
NON_BEAN_KEYWORDSで除外済み)としてのみ現存することを確認した。残る
対象は6件(Honduras Kukurucho Geisha・Kenya Nyeri Tegu・Burundi Kayave・
Ethiopia Bench Maji・【Decaf】Ethiopia Sidamo・Assemblage Blend)。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象6件全てでテイスティング文・産地
情報が入っている。うち3件は末尾に「内容量：<重量>g」という内容量表記
(場合によっては続けて配送案内)が付くため、この表記の直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "SAFARI COFFEE ROASTER",
    "url": "https://safaricoffee.theshop.jp/",
    "platform": "theShop",
    "address": "大分県大分市畑中3丁目2番7号コーポ森101",
    "prefecture": "大分県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE/theShop系店舗と同一の"
                          "記述。curl/python-requests等は個別にDisallow: /指定"
                          "あり、本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://safaricoffee.theshop.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "COLD BREW", "Subscription", "定期", "Latte Base", "Drip Bag",
    "Whole Sale", "Anniversary Selection",
]
WEIGHT_PATTERN = re.compile(r"\((\d+)\s*g\)", re.IGNORECASE)
TRAILING_WEIGHT_PATTERN = re.compile(r"\s*\(\d+\s*g\)\s*$", re.IGNORECASE)
FLAVOR_STOP_PATTERN = re.compile(r"内容量：\d+g")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(title: str, price: int | None, product_url: str, flavor_notes: str | None = None) -> dict | None:
    if not WEIGHT_PATTERN.search(title):
        # 重量表記の無い商品(定期購入・Latte Base等)は対象外
        return None
    base_name, weight_g = base_name_and_weight(title)
    if not base_name:
        return None
    parsed = parse_product(base_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(base_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        title = fields["title"]
        if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
            continue
        detail = build_record(title, fields["price"], product_url, fields.get("flavor_notes"))
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
    with open("data_safaricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_safaricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
