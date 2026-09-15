# -*- coding: utf-8 -*-
"""
scrape_watarucoffee.py

コーヒー焙煎研究所わたる(watarucoffee-onlinestore.com、〒861-4114 熊本県
熊本市南区野田2丁目30-31 フロンティアビル2F、自家焙煎豆のオンライン販売)
の商品情報を取得する。カラーミーショップ(shop-pro.jp、独自ドメイン)。

【住所について】
特定商取引法ページ(https://watarucoffee-onlinestore.com/?mode=sk)で実データ
確認済み(2026-09時点): 「住所」欄に郵便番号「861-4114」・住所「熊本県熊本市
南区野田2丁目30-31フロンティアビル2F」との記載を確認。候補リストの住所
(南区野田2丁目30-31 フロンティアビル2F)と一致。運営統括責任者名:毛山剛。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述
(User-agent: *はDisallow: /secure/, /cart/のみ)。本スクレイパーは識別可能な
独自User-Agentを使用する。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=euc-jp)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み(2026-09時点): トップページのカテゴリ一覧は以下7件。
・コーヒー豆(cbid=2666252) ← 対象
・コーヒー器具(cbid=2678097) 非対象(器具)
・WATARUオリジナルグッズ(cbid=2685657) 非対象(グッズ)
・コーヒーギフト(cbid=2685894) 非対象(ギフトセット)
・コーヒー定期購入(cbid=2685922) 非対象(定期購入)
・販売終了したコーヒー豆(cbid=2697146) 非対象(販売終了)
・販売終了したグッズ・コーヒー器具(cbid=2790588) 非対象(販売終了・グッズ)
「コーヒー豆」カテゴリのみを対象とする。

【重量について】
実データ確認済み: kiyacoffee.pyと同様、商品名に重量表記が無く、variants配列
のtitle(例:「そのまま　×　100g」)に挽き方と重量が両方含まれる。product自体の
sales_price_including_taxは最小重量バリアントの価格と一致するため、同じ方式
(最小価格帯の中から最小重量のバリアントを採用)で重量を取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "コーヒー焙煎研究所わたる",
    "url": "https://watarucoffee-onlinestore.com/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "熊本県熊本市南区野田2丁目30-31 フロンティアビル2F",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述。User-agent: *はDisallow: /secure/, "
                          "/cart/のみ)",
}

BASE_URL = "https://watarucoffee-onlinestore.com"
BEAN_CATEGORY_IDS = ["2666252"]  # コーヒー豆
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "ドリップバッグ", "ドリップバック", "ギフト", "アソート", "詰め合わせ", "定期"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=euc-jp)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list(cid: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    for link in soup.select('a[href*="pid="]'):
        href = link.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not m:
            continue
        product_url = f"{BASE_URL}/?pid={m.group(1)}"
        if product_url not in seen:
            seen.add(product_url)
            urls.append(product_url)
    return urls


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def _weight_from_title(title: str) -> int | None:
    m = re.search(r"(\d+)\s*[Kk][Gg][ｇ]?", title)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", title)
    return int(m.group(1)) if m else None


def pick_min_price_weight(product: dict, price: int | None) -> int | None:
    variants = product.get("variants") or []
    candidates = [v for v in variants if v.get("option_price_including_tax") == price]
    pool = candidates or variants
    if not pool:
        return None
    variant = min(pool, key=lambda v: v.get("option_price_including_tax") or float("inf"))
    return _weight_from_title(variant.get("title") or "")


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")

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

    weight_g = pick_min_price_weight(product, price)
    structural_out_of_stock = product.get("stock_num") == 0
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
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return None
    return build_record(url, colorme_product)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls: list[str] = []
    seen: set[str] = set()
    for cid in BEAN_CATEGORY_IDS:
        for url in scrape_category_list(cid):
            if url not in seen:
                seen.add(url)
                product_urls.append(url)

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json as json_module

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_watarucoffee.json", "w", encoding="utf-8") as f:
        json_module.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_watarucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
