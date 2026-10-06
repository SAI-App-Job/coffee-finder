# -*- coding: utf-8 -*-
"""
scrape_cossettecoffee.py

COSSETTE COFFEE(コゼットコーヒー、cossette.theshop.jp、北海道登別市富士町4丁目15-2、
自家焙煎珈琲店・独自設計の直火式焙煎機)の商品情報を取得する。BASE(theshop.jpドメイン)。

【住所について】
/law(特定商取引法に基づく表記)はBASE社の住所(東京都港区六本木)が記載されるため使えない。
店舗紹介ページ(/p/00003、ACCESS)で実データ確認済み(2026-10時点):
「北海道登別市富士町４丁目１５−２」「JR北海道幌別駅」との記載を確認。
(/p/00001はショッピングガイドで住所の記載なし)

【対象商品について】
実データ確認済み(2026-10時点): 全4商品(オリジナルブレンド200g/300g、ブラジル・トミオフクダDOT
200g/300g)のうち、銘柄ごとに最小重量(200g)の商品を代表とする2件をITEMSに明示している。
粉の取り扱いは無く豆のみ。商品名・価格・在庫(item_purchasability)・説明は商品ページ
(og:title / product:price:amount / og:description)から取得する。焙煎度は商品名の【中深煎り】
から取得する(オリジナルブレンドは記載なし)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
    extract_from_description,
)

SHOP_INFO = {
    "name": "COSSETTE COFFEE",
    "url": "https://cossette.theshop.jp/",
    "platform": "BASE",
    "address": "北海道登別市富士町4丁目15-2",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cossette.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 重量(g), 分類の上書き(Noneなら自動判定))
ITEMS = [
    ("73342926", 200, "ブレンド"),  # オリジナルブレンド200g(300gは65626928)
    ("73342767", 200, None),        # ブラジル・トミオフクダDOT 200g(300gは65628142)
]

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
_ROAST_WORD = r"(?:極深煎り|中深煎り|中浅煎り|中煎り|浅煎り|深煎り)"
ROAST_PATTERN = re.compile(rf"(?:焙煎度|焙煎)\s*[：:]?\s*({_ROAST_WORD}(?:[～〜~]{_ROAST_WORD})?)")
ROAST_HEAD_PATTERN = re.compile(rf"(?:やや)?{_ROAST_WORD}")  # 説明文の冒頭(商品名の直後)に焙煎度が書かれる形式
_ROAST_ENG = r"(?:フルシティ|シティ|ミディアムハイ|ミディアム|ハイ|ライト|シナモン|フレンチ|イタリアン)ロースト"
ROAST_LABEL_PATTERN = re.compile(rf"焙煎度\s*[：:]\s*((?:{_ROAST_ENG}[\s・/]*)+)")
ROAST_NAME_PATTERN = re.compile(_ROAST_ENG)


def clean(text: str) -> str:
    text = html.unescape(text).replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def build_record(item_id: str, weight_g: int, category_override: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = clean(title_m.group(1))
    title = re.sub(r"\s*\|\s*[^|]*powered by BASE\s*$", "", title)
    title_roast = ROAST_HEAD_PATTERN.search(title)  # 商品名の【浅煎り】等の表記
    name = re.sub(r"\s*[|｜]?\s*コーヒー豆\s*\d+g\s*$", "", title)
    name = re.sub(rf"【(?:やや)?{_ROAST_WORD}】\s*", "", name)
    name = re.sub(r"^リニューアル[！!]\s*", "", name)
    name = re.sub(r"\s*[\d０-９]+\s*[gｇ]\s*$", "", name)
    name = re.sub(r"\s*[|｜]\s*", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    desc_m = DESC_PATTERN.search(html_text)
    full_desc = clean(desc_m.group(1)) if desc_m else ""
    desc = full_desc[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            detected = detect_country_name(full_desc)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
        if not parsed["processing_method"]:
            # 説明文冒頭(商品名の直後)の表記から補う。それが無ければ「精選:」等の書式で探す
            pm = detect_processing_method(full_desc[:120]) or extract_from_description(full_desc)["processing_method"]
            if pm and pm.lower().startswith("wash"):
                pm = "ウォッシュド"  # 説明文が「精選：Wash」で途切れている(Washed/ウォッシュドの意)
            parsed["processing_method"] = pm

    roast_level = parsed["roast_level"] or (title_roast.group(0) if title_roast else None)
    if not roast_level:
        rl = ROAST_LABEL_PATTERN.search(full_desc)
        rm = ROAST_PATTERN.search(full_desc)
        if rl:
            roast_level = "・".join(rl.group(1).split())
        elif rm:
            roast_level = rm.group(1)
        else:
            rn = ROAST_NAME_PATTERN.search(full_desc)
            rh = ROAST_HEAD_PATTERN.search(full_desc[:200])
            if rn:
                roast_level = rn.group(0)
            elif rh:
                roast_level = rh.group(0)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, weight_g, category_override in ITEMS:
        try:
            record = build_record(item_id, weight_g, category_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cossettecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cossettecoffee.json に出力しました")


if __name__ == "__main__":
    main()
