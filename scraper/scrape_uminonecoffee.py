# -*- coding: utf-8 -*-
"""
scrape_uminonecoffee.py

UMINONE Coffee Wine cellar(ウミノネコーヒー、uminone.co.jp、運営：株式会社
UMINONE、自家焙煎豆のオンライン販売、ワイン・薬膳カレーも併売するカフェ)の
商品情報を取得する。

【プラットフォームについて】
scrape_tsubameroaster.pyと同一の独自ASP(株式会社アイフラッグ「ホームページ
マイスター for ネットショップ」、ドメインxaas3.jp)を使用していることを
実データ確認済み。HTML構造(ul.itemList > li、p.name>a、p.price)も同一。

【住所について】
候補リストでは実店舗(カフェ)の住所として「山口県下関市観音崎町10-11」が
挙がっていたが、公式ストアの特定商取引法ページ(https://www.uminone.co.jp/
info.html)で実データ確認したところ(2026-09時点)、「販売業者 株式会社
UMINONE / 販売責任者 中村芳樹 / 所在地　〒751-0816 山口県下関市椋野町
1丁目30番25号」であることが分かった。カフェの実店舗住所(観音崎町10-11、
アルコール販売に関する開示箇所で確認)とは異なる、通信販売事業者としての
登録住所と考えられる。本プロジェクトの既定方針(手掛かりが競合する場合は
事業者本人が届け出た特定商取引法上の所在地を優先)に従い、tokushoho記載の
椋野町側を採用する。

robots.txt確認済み(2026-09時点): 他の同ASP店舗(燕珈琲)と同一の記述。
User-agent: *に対し/default/error/・/preview/のみDisallow。それ以外は
制限なし。

【商品カテゴリの構成について】
実データ確認済み(2026-09時点): Category 1(コーヒー、全11件)が唯一の
コーヒー豆カテゴリ。Category 2(飲み比べセット)・Category 3(定期便)・
Category 4/5(焙煎度合いから選ぶ)はCategory 1の商品を別軸で再掲したビュー
(重複)のため、Category 1のみをクロール対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み(Category 1、全11件): 2種類/3種類/5種類の「コーヒー豆
飲み比べセット」(複数銘柄の詰め合わせ)3件、「【定期便】プレミアムブレンド
100g＋オススメのシングルオリジン100g」1件がNON_BEAN_KEYWORDSで除外される。
残り7件(ストレート800gの単一銘柄6種＋顔の見えるスペシャルティーコーヒー
200gエチオピア1種)を対象とする。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 商品詳細ページのdiv.mainTxt内にテキストがあるが、
ストレート800gの6件(ホンジュラス/エチオピア/グアテマラ/タイ/
インドネシア/ブラジル)は産地が異なるにもかかわらず「【あなたの毎日に、
焙煎したての感動を。】…」から始まる文言が一字一句同一で、産地固有の
テイスティング情報を含まない汎用的な焙煎方針の宣伝文であることを
確認した。これらはGENERIC_PLACEHOLDER_TEXTとして判定しflavor_notes=
nullとする。唯一「顔の見えるスペシャルティーコーヒー200ｇ エチオピア
イルガチェフェ ナチュラル」のみ産地・精製方法・香味等の商品固有の
テイスティング文を含むため、こちらのみ全文を採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "UMINONE Coffee Wine cellar",
    "url": "https://www.uminone.co.jp/",
    "platform": "ホームページマイスター for ネットショップ(株式会社アイフラッグ、独自ASP)",
    "address": "山口県下関市椋野町1丁目30番25号",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/・/preview/のみ"
                          "Disallow、それ以外は制限なし。Crawl-delayの指定なし)",
}

BASE_URL = "https://www.uminone.co.jp"
COFFEE_CATEGORY_URL = f"{BASE_URL}/category/1"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["飲み比べセット", "定期便"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"販売価格[：:]\s*([\d,]+)\s*円")
# 実データ確認済み(理由はdocstring参照): 産地の異なる6商品で一字一句同一の汎用文
GENERIC_PLACEHOLDER_TEXT = (
    "【あなたの毎日に、焙煎したての感動を。】\n"
    "焙煎当日出荷のスペシャリティコーヒーをお届けします。\n"
    "焙煎したての新鮮なコーヒーを楽しめます。\n"
    "焙煎したコーヒーは、出荷当日に新鮮な状態でお届けするため、毎日異なる香りと味わいをご家庭で体験いただけます。\n"
    "一週間程度の熟成期間を経て、コーヒーの風味が一層引き立ち、あなたの朝のコーヒータイムを特別なものに変えます。\n"
    "お気に入りの焙煎スタイルをお選びいただき、コーヒーの魅力を存分にお楽しみください！\n"
    "出荷当日に深く煎ることで、香ばしさを出しつつ酸味を残した風味となっております。\n"
    "口にしたときの一口目で、苦味と酸味がちゃんと立ち、香り強さも楽しんでいただけます。\n"
    "届いた直後は、焙煎の過程で発生したガスが含まれるため荒々しさがありますが、次第に味と香りに変化が現れます。\n"
    "コーヒー豆の熟成の過程、ソムリエが大事にしている「香り」を存分にご堪能ください。"
)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(COFFEE_CATEGORY_URL)
    results = []
    for li in soup.select("ul.itemList > li"):
        name_el = li.select_one("p.name > a")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        price_el = li.select_one("p.price")
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        out_of_stock_img = li.select_one('img[alt*="在庫切れ"]')

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "structural_out_of_stock": out_of_stock_img is not None,
        })
    return results


def extract_flavor_notes(product_url: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = fetch_page(product_url)
    el = soup.select_one("div.mainTxt")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    if text == GENERIC_PLACEHOLDER_TEXT:
        return None
    return text.strip() or None


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])
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
        "flavor_notes": extract_flavor_notes(item["product_url"]),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_item_list()

    records = []
    flavored_records = []
    for item in items:
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
    with open("data_uminonecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_uminonecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
