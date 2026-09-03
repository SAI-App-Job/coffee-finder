# -*- coding: utf-8 -*-
"""
scrape_ennoki.py

焙煎処 縁の木(ennoki.shop-pro.jp、東京都台東区蔵前、就労支援を兼ねた焙煎所)の
商品情報を取得する。カラーミーショップ(shop-pro.jpレガシードメイン)の
新しいテーマバリエーション(`li.c-item-list__item`/`.c-item-list__ttl`/
`.c-item-list__price`。既存店舗で確認済みの`li.prd_lst_unit`等とは異なる)。
文字コードはEUC-JPのため、requestsのデフォルト推定に任せず明示的に指定する。

robots.txt確認済み(2026-09時点): /secure/・/cart/のみDisallow(User-agent: *)。
AhrefsBot/DotBot/MegaIndex/MJ12bot/PetalBot/SemrushBot/SEOkicks/serpstatbotを
個別にDisallow: /。それ以外は制限なし。

【カテゴリ構造について】
実データ確認済み: メガメニューに「豆」「定期便コース」「お菓子」「ギフト」
「アルコールギフト」「コーヒー関連」「KURAMAEモデルグッズ」
「全国福祉事業所の自主生産品」「その他」の9カテゴリがあり、「豆」
(cbid=2897178)のみがコーヒー豆(52件、5ページ)。他は非コーヒー豆商品の
ため対象外(カテゴリ単位で絞り込み可能、GONZO/BEANS珈琲のような
sitemap全件+キーワード除外は不要)。「豆」カテゴリ内も1件のみ3種詰め合わせの
お試しセットが混在するためNON_BEAN_KEYWORDSで除外する。

【焙煎度・挽き方が選択式である点について】
実データ確認済み: 商品詳細ページに埋め込まれたJS変数`var Colorme = {...}`の
`product.variants`が「内容量(200g/400g/800g、ドリップパック形態含む)」と
「焙煎度合い(シナモン〜イタリアン、オーナーにお任せ含む全8種)」の組み合わせで、
価格は内容量のみで決まり焙煎度では変わらない(実データ確認済み、全焙煎度で
同額)。商品名自体には焙煎度が含まれないため、roast_selectable=Trueとし
roast_levelはparse_product()の商品名解析結果(Noneになることが多い)に任せる。

【重量・価格について】
実データ確認済み: `product.variants[].option1_value`が内容量を表す文字列
(例:"200g"/"200g（ドリップパック）"/"400g（10％お得）")。ドリップパック形態は
豆そのものではなくパッケージ形態が異なる別商品的な扱いのため除外し、
重量が最小の通常(豆のまま)バリエーションを代表として採用する。

【在庫について】
実データ確認済み: `inventory_control`が店舗単位で"none"(stock_num常にnull)。
Roast Design Coffee・Coulaneと同じパターンで、構造化された在庫フラグは
使えないため商品名のテキストのみで在庫判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "焙煎処 縁の木",
    "url": "https://ennoki.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "東京都台東区蔵前",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみDisallow。"
                          "AhrefsBot等一部ボットを個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://ennoki.shop-pro.jp"
BEAN_CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2897178&csid=0"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["お試しセット"]

COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
GRAM_PATTERN = re.compile(r"(\d+)\s*g")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list() -> list[dict]:
    results = []
    page = 1
    while True:
        url = BEAN_CATEGORY_URL if page == 1 else f"{BEAN_CATEGORY_URL}&page={page}"
        soup = fetch_page(url)
        items = soup.select("li.c-item-list__item")
        if not items:
            break
        for item in items:
            link_el = item.select_one(".c-item-list__ttl a")
            if not link_el:
                continue
            href = link_el.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if not m:
                continue
            product_url = f"{BASE_URL}/?pid={m.group(1)}"
            results.append({
                "raw_name": link_el.get_text(strip=True),
                "product_url": product_url,
            })
        if not soup.select_one(f'a[href*="page={page + 1}"]'):
            break
        page += 1
    return results


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    candidates = []
    for v in variants:
        option1 = v.get("option1_value") or ""
        if "ドリップ" in option1:
            continue
        m = GRAM_PATTERN.search(option1)
        if not m:
            continue
        candidates.append((int(m.group(1)), v))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title:
        return None

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
            "price": None,
            "product_url": product_url,
        }

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    if variant is not None:
        price = variant.get("option_price_including_tax") or variant.get("option_price")
        weight_m = GRAM_PATTERN.search(variant.get("option1_value") or "")
        weight_g = int(weight_m.group(1)) if weight_m else None
    else:
        price = product.get("sales_price_including_tax") or product.get("sales_price")
        weight_g = None

    stock_status = detect_stock_status(title, False)

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
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(item["product_url"])
            detail = build_record(soup, item["product_url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue

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
        url = sys.argv[1]
        result = build_record(fetch_page(url), url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_ennoki.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_ennoki.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
