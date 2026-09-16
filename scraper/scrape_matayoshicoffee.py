# -*- coding: utf-8 -*-
"""
scrape_matayoshicoffee.py

又吉コーヒー園(matayoshicoffee.jp、沖縄県国頭郡東村字慶佐次718-28)の商品情報を
取得する。独自ドメイン・独自カート(xaas3.jpという小規模事業者向けASPカート
基盤上に構築、実データ確認済み)。沖縄県内で自ら栽培・精製・焙煎まで行う、
数少ない国産(沖縄産)コーヒー農園の直営ショップ。

【文字コードについて】
実データ確認済み: HTTPヘッダにcharset指定が無く(Content-Type: text/htmlのみ)、
requestsの自動判定はISO-8859-1にフォールバックしてしまう。metaタグでは
「charset=utf-8」と明記されているため、明示的にresp.encoding="utf-8"を
設定する(本プロジェクトで頻発する既知の文字化けパターン)。

【商品一覧・詳細ページについて】
実データ確認済み: 商品はすべて`/category/1/`の単一カテゴリに掲載されている
(全16件、ページネーションなし)。一覧ページの商品名だけでも産地・精製方法の
情報は十分だが、在庫状態(li.stock1、「在庫あり」/「在庫切れ」)と正式な商品名
(li.name span.data)・価格(li.sales_price)は詳細ページ側の方が構造化されて
確実に取得できるため、詳細ページを個別に取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全16件): 又吉CLUB(定期便的な福袋セット)・オリジナルTシャツ
(2種)・トートバッグ・コーヒーノキの葉っぱのお茶(コーヒー豆ではない、2種)・
コーヒー苗(ブルボン種の苗木、植物そのものであり焙煎豆ではない、2種)・
コーヒーちんすこう(コーヒー粉入りの菓子)がNON_BEAN_KEYWORDSで除外される。
残り7件(沖縄県産100%ストレート1種＋沖縄豆配合ブレンド1種＋海外産ストレート
5種、いずれも自家焙煎)を対象とする。

【沖縄県産(国産)コーヒーについて】
実データ確認済み: 「【10年越しの初出し商品】...沖縄豆100%　又吉コーヒー園で
栽培、精製、焙煎した希少な豆」(item/okinawa/)は、又吉コーヒー園自身が沖縄県内で
栽培した豆を自家焙煎した完全国産コーヒー。coffee_parserの国名辞書には「沖縄」
「日本」が(他店舗での誤爆リスクを避けるため)登録されていないため、この店舗
限定でローカルに「日本(沖縄県)」を検出する。「又吉ブレンド」(item/blend01/)は
沖縄豆と海外豆をブレンドした商品のため、BLEND_KEYWORDSの「ブレンド」で
category="ブレンド"と自動判定される(産地は単一に確定できないためnullのまま)。

robots.txt確認済み(2026-09時点): User-Agent: * で/default/error/と/preview/
のみDisallow、他は制限なし。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "又吉コーヒー園",
    "url": "https://www.matayoshicoffee.jp/",
    "platform": "独自カート(xaas3.jp)",
    "address": "沖縄県国頭郡東村字慶佐次718-28",
    "prefecture": "沖縄県",
    "robots_txt_status": "許可(2026-09確認。User-Agent: * で/default/error/と/preview/"
                          "のみDisallow、他は制限なし)",
}

BASE_URL = "https://www.matayoshicoffee.jp"
CATEGORY_URL = f"{BASE_URL}/category/1/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 実データ確認済み(理由はdocstring参照)。「シャツ」は「Ｔシャツ」(全角T)と
# 「Tシャツ」(半角T)の表記ゆれ両方を1語で拾うため、T抜きのキーワードにしている
NON_BEAN_KEYWORDS = ["CLUB", "シャツ", "トートバッグ", "葉っぱ", "苗", "ちんすこう"]

LIST_ITEM_PATTERN = re.compile(
    r'<p class="name">\s*<a href="([^"]+)"[^>]*>([^<]+)</a>', re.DOTALL
)
NAME_DETAIL_PATTERN = re.compile(
    r'<li class="name">.*?<span[^>]*>([^<]+)</span>', re.DOTALL
)
PRICE_DETAIL_PATTERN = re.compile(r'<li class="sales_price">.*?<span>([\d,]+)円', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # 実データ確認済み(理由はdocstring参照)
    return resp.text


def fetch_list_items() -> list[dict]:
    text = fetch_text(CATEGORY_URL)
    items = []
    for url, title in LIST_ITEM_PATTERN.findall(text):
        title = title.strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        items.append({"list_title": title, "product_url": url})
    return items


def fetch_detail(url: str) -> dict:
    text = fetch_text(url)
    name_m = NAME_DETAIL_PATTERN.search(text)
    price_m = PRICE_DETAIL_PATTERN.search(text)
    out_of_stock = "在庫切れ" in text and "在庫あり" not in text
    return {
        "raw_name": name_m.group(1).strip() if name_m else None,
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "out_of_stock": out_of_stock,
    }


def detect_okinawa_origin(title: str) -> bool:
    # 実データ確認済み: 「沖縄豆100%」かつ「又吉コーヒー園で栽培」等、自園で
    # 栽培から焙煎まで行った沖縄県産100%の豆であることが明記されている商品
    return "沖縄豆100" in title and "栽培" in title


def build_record(item: dict, detail: dict) -> dict | None:
    title = detail["raw_name"] or item["list_title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": detail["price"],
            "product_url": item["product_url"],
        }

    if not parsed["origin_country"] and parsed["category"] != "ブレンド" and detect_okinawa_origin(title):
        parsed["origin_country"] = "日本(沖縄県)"
        parsed["origin_source"] = "country_name"

    parsed = apply_category_hint_fallback(parsed, None)

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": item["product_url"],
        }

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    stock_status = detect_stock_status(title, detail.get("out_of_stock", False))

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
        "price": detail["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = fetch_list_items()

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        try:
            detail = fetch_detail(item["product_url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        detail_record = build_record(item, detail)
        if detail_record is None:
            continue
        if detail_record.get("non_bean"):
            non_bean_records.append(detail_record)
        elif detail_record.get("is_flavored"):
            flavored_records.append(detail_record)
        else:
            records.append(detail_record)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_matayoshicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matayoshicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
