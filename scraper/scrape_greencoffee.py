# -*- coding: utf-8 -*-
"""
scrape_greencoffee.py

green coffee(www.green-web.jp、広島県広島市南区段原の自家焙煎コーヒー豆店)の商品情報を取得する。
BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品11件のうち、200g表記の焙煎豆10件
(ブレンド5・ストレート5)を対象とする。「ギフト箱 各種」は除外。コーヒーバッグ・リキッド等は
sitemapに商品が存在しない。全商品が200g固定の1商品(数量で追加購入)で、重量違いの重複は無い。
商品ページに「種類: 粉/豆」の選択肢があるが、粉は同一商品のバリエーションのため豆のみ扱う。

【説明文・焙煎度について】
og:descriptionは全商品共通の店紹介文のため使わず、本文の商品説明(「PAY IDはBASEのサービスです」の
直後から「─ ◎配送について」(無い商品は「種類 粉 豆」)の直前)を取得する。焙煎度は商品名・説明文に「深煎り」等の記載がある
場合のみroast_hintとして保持する(記載の無い商品はNone)。焙煎度は選択式ではない。

【価格について】
表示価格は税込(特商法の表記は「表示価格/消費税込」)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "green coffee",
    "url": "https://www.green-web.jp/",
    "platform": "BASE",
    "address": "広島県広島市南区段原一丁目5-7 KSビルド1F",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.green-web.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_HINT_PATTERN = re.compile(r"(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
EXCLUDE_KEYWORDS = ["ギフト箱"]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def extract_description(html_text: str) -> str | None:
    body = re.sub(r"<style.*?</style>|<script.*?</script>", "", html_text, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
    m = re.search(r"PAY IDはBASEのサービスです\s*(.*?)\s*(?:─\s*◎配送について|種類 粉 豆)", text)
    return m.group(1).strip() if m and m.group(1).strip() else None


def build_record(item_url: str) -> dict | None:
    html_text = fetch(item_url)
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).split(" | ")[0]).strip()
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    weight_m = WEIGHT_PATTERN.search(title)
    if not weight_m:
        return None
    weight_g = int(weight_m.group(1))

    desc = extract_description(html_text)
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

    hint_m = ROAST_HINT_PATTERN.search(title) or (ROAST_HINT_PATTERN.search(desc) if desc else None)
    roast_hint = hint_m.group(1) if hint_m else None

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
        "flavor_notes": desc[:400] if desc else None,
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
    with open("data_greencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_greencoffee.json に出力しました")


if __name__ == "__main__":
    main()
