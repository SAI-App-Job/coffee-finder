# -*- coding: utf-8 -*-
"""
scrape_beanscoffeecompany.py

ビーンズコーヒーカンパニー(beanscoffee.official.ec、広島県福山市新市町、(有)ビーンズコーヒーカンパニー)の
自家焙煎コーヒー豆の商品情報を取得する。BASE(official.ec ドメイン)。
(同名の別店「scrape_beanscoffee.py」とは別の店舗)

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
特定商取引法に基づく表記(/law)で実データ確認済み(2026-10時点): 「事業者の所在地
〒729-3101 広島県福山市新市町戸手780-1」(会社名 (有)ビーンズコーヒーカンパニー)。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品84件のうち、焙煎豆は同一銘柄が100g/250g/500gの
別商品として登録されている(10銘柄×3重量=約30件。タンザニアのみ500g商品名に等級表記なし)。
各銘柄の最小重量である100gを代表として採用する(10件=ストレート6・ブレンド4)。
除外: ドリップバッグ・リキッドアイス・ギフト・福袋・お試しセット・器具・濾紙・雑貨・菓子・シュガー、
および250g/500gの重量違い商品。
「ブラジル サンタカタリーナ農園 キャラメード デカフェ」(¥315)は商品ページに重量・内容量の
記載が一切なく、価格が100g相当とは考えにくい(用途不明)ため、価格・重量を捏造せず対象外とした。

【焙煎度・説明文について】
説明文(og:description)に「ロースト 浅煎り/中煎り/深煎り」の記載があるため、roast_hintに保持する。
「味の特徴 ロースト」欄が無い商品は、説明文中の焙煎度表記が1種類だけの場合のみ採用し、それ以外はNone。「コーヒーの状態」(豆のまま/挽き)は同一商品の選択肢。

【価格について】
表示価格は税込(特商法の表記は「販売価格は税込み表記」)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ビーンズコーヒーカンパニー",
    "url": "https://beanscoffee.official.ec/",
    "platform": "BASE",
    "address": "広島県福山市新市町大字戸手780-1",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://beanscoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
# 代表重量(各銘柄の最小重量)。商品名に「100g」(全角ｇ含む)があるものだけが対象
TARGET_WEIGHT_PATTERN = re.compile(r"(?<!\d)100\s*g")
ROAST_HINT_PATTERN = re.compile(r"ロースト\s*(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ANY_ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_KEYWORDS = ["ドリップバッグ", "ギフト", "リキッド", "福袋", "セット"]
# coffee_parser.pyの国名辞書で検出できない表記
ORIGIN_OVERRIDES = {"ガテマラ": "グアテマラ"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def build_record(item_url: str) -> dict | None:
    html_text = fetch(item_url)
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title_m.group(1).split(" | ")[0])).strip()
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    if not TARGET_WEIGHT_PATTERN.search(title):
        return None
    weight_g = 100

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if kw in title:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break

    compact_desc = desc.replace(" ", "")
    roast_m = ROAST_HINT_PATTERN.search(compact_desc)
    roast_hint = roast_m.group(1) if roast_m else None
    if roast_hint is None:
        # 「味の特徴 ロースト」欄の無い商品は、説明文中の焙煎度表記が1種類だけの場合に限り採用する
        mentioned = set(ANY_ROAST_PATTERN.findall(compact_desc))
        if len(mentioned) == 1:
            roast_hint = mentioned.pop()

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
        "roast_hint": roast_hint,
        "roast_selectable": False,
        "flavor_notes": desc[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    sitemap = fetch(f"{BASE_URL}/sitemap.xml")
    item_urls = re.findall(r"<loc>([^<]*/items/\d+)</loc>", sitemap)
    records = []
    for item_url in item_urls:
        try:
            record = build_record(item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beanscoffeecompany.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beanscoffeecompany.json に出力しました")


if __name__ == "__main__":
    main()
