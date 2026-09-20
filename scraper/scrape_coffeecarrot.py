# -*- coding: utf-8 -*-
"""
scrape_coffeecarrot.py

珈琲きゃろっと(coffeecarrot.jp、北海道恵庭市恵み野西1-25-2、EC-CUBE)の
商品情報を取得する。九州(福岡)地方の調査で同名の別店舗を「対象地域外」
として除外した実績があるが、本店舗は北海道恵庭市恵み野が本拠地であり、
今回のSapporo/中央北海道バッチの対象として正しい(特定商取引法ページ
https://coffeecarrot.jp/order/ で住所を実データ確認済み、2026-09時点、
〒061-1373 北海道恵庭市恵み野西1-25-2)。

【プラットフォームについて】
フレッシュローストコーヒー豆の木(scrape_mamenoki.py)と同じEC-CUBE系
テーマ(div.list_areaにh3 a名前+span[id^="price02_default_"]価格が
一覧ページのみで完結)。

【対象商品について】
実データ確認済み(全27件、pageno=1・2の2ページ): 単一銘柄の200gコーヒー豆
18件と、非対象の「お楽しみセット」(複数銘柄詰め合わせ)、「Cafest/
Dark Cafest」(365ml、瓶入りリキッドコーヒー)、「水出しアイスコーヒー
パック」(コールドブリューパック、量り売りの豆ではない)、「オリジナル
ドリップバッグ」(個包装ドリップ)。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): User-agent: *で/cart/等の管理・購入系
パスのみDisallow、商品一覧ページ(/products/)は制限対象外。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 一覧ページのみの取得だったが、詳細ページ
(products/detail.php?product_id=N)のdiv.product_copy > h2に短い
キャッチコピー(テイスティングの要約)、div.main_commentに焙煎人の
コメント全文(産地・生産者のストーリーとテイスティング表現が地の文で
混在)が入っている。対象19件全てで確認、綺麗な見出し区切りは無いため
「背景説明とテイスティング文が混在する場合は全文採用」の既存方針
(バッチ85-120等)に倣い、両方を連結して採用する。og:descriptionは
店舗共通の固定文(商品に依存しない)のため使用不可。flavor_notes取得の
ため新たに詳細ページへの個別アクセスを追加した(一覧ページのみだった
既存実装を拡張)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲きゃろっと",
    "url": "https://coffeecarrot.jp/",
    "platform": "EC-CUBE",
    "address": "北海道恵庭市恵み野西1-25-2",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *で/cart/等の管理・"
                          "購入系パスのみDisallow、/products/配下は制限対象外)",
}

BASE_URL = "https://coffeecarrot.jp"
LIST_PAGES = [
    f"{BASE_URL}/products/list.php",
    f"{BASE_URL}/products/list.php?category_id=0&pageno=2",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "ml", "パック"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(product_url: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    try:
        soup = fetch_page(product_url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
        return None
    copy_el = soup.select_one("div.product_copy h2")
    comment_el = soup.select_one("div.main_comment")
    parts = [
        el.get_text(" ", strip=True)
        for el in (copy_el, comment_el)
        if el and el.get_text(strip=True)
    ]
    return " ".join(parts) or None


def build_record(box) -> dict | None:
    h3a = box.select_one('h3 a[href*="product_id="]')
    if not h3a:
        return None
    title = h3a.get_text(strip=True)
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    href = h3a.get("href", "")
    product_url = f"{BASE_URL}{href}" if href.startswith("/") else href

    price_span = box.select_one('span[id^="price02_default_"]')
    price = None
    if price_span:
        m = re.search(r"[\d,]+", price_span.get_text())
        if m:
            price = int(m.group().replace(",", ""))

    structural_out_of_stock = box.select_one("div.cartbtn.attention") is not None

    parsed = parse_product(title)

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
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
        "flavor_notes": extract_flavor_notes(product_url),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records_by_url: dict[str, dict] = {}
    flavored_by_url: dict[str, dict] = {}

    for url in LIST_PAGES:
        try:
            soup = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            continue
        for box in soup.select("div.list_area"):
            detail = build_record(box)
            if detail is None:
                continue
            if detail.get("is_flavored"):
                flavored_by_url.setdefault(detail["product_url"], detail)
            else:
                records_by_url.setdefault(detail["product_url"], detail)

    return list(records_by_url.values()), list(flavored_by_url.values())


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeecarrot.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeecarrot.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
