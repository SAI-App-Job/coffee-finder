# -*- coding: utf-8 -*-
"""
scrape_birdbethere.py

Bird be There(https://birdbethere.base.shop/、鹿児島県霧島市隼人町神宮3-2-3、
公式サイトなし)の自家焙煎コーヒー豆の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

【住所について】
BASEの特商法ページ(/law)はBASE社の住所(東京都港区六本木)のみで店舗の住所ではない。
店舗住所は第三者の一覧サイト(shingakunet.com 霧島市のカフェ一覧)の
「鹿児島県霧島市隼人町神宮3丁目2-3」を採用(2026-10-13確認。依頼者提供の情報とも一致。
公式サイトでの確認はできていない)。

【対象商品について】
sitemap.xml の商品7件のうち、コーヒー豆4銘柄(いずれも150g・1,300円)を対象とする。
水出しコーヒー6パック・オリジナルTシャツ(2件)は除外。
各商品は「豆/粉」の選択式で、先頭の「豆」バリエーションの在庫で販売状況を判定する
(ペルー ブルボンスペシャルは豆150gが在庫なし・粉150gのみ在庫あり → 品切れ扱い)。
商品名は商品ページのタイトルから重量表記を除いたもの。
焙煎度の記載は マンデリン(☆深煎り フルシティーロースト)のみ。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import html as _html
import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "Bird be There",
    "url": "https://birdbethere.base.shop/",
    "platform": "BASE",
    "address": "鹿児島県霧島市隼人町神宮3-2-3",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://birdbethere.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ITEM_IDS = ["85037661", "68251745", "92567243", "66399482"]
WEIGHT_G = 150

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_NAME = re.compile(r'cot-itemOrder-variationName"[^>]*>([^<]*)')
VARIATION_STOCK = re.compile(r'cot-itemOrder-variationStock"[^>]*>([^<]*)')


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def field(desc: str, key: str, stop: str):
    m = re.search(key + r"\s*[:：]?\s*(.+?)(?=" + stop + r"|$)", desc)
    return clean(m.group(1)) if m else None


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    t = resp.text
    title = clean(_html.unescape(TITLE_PATTERN.search(t).group(1)))
    title = re.sub(r"\s*\|.*$", "", title)
    name = clean(re.sub(r"\s*150\s*g\s*$", "", title, flags=re.IGNORECASE))
    desc = clean(_html.unescape(DESC_PATTERN.search(t).group(1)))
    price_m = PRICE_PATTERN.search(t)
    pm = PURCHASABILITY_PATTERN.search(t)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"
    names, stocks = VARIATION_NAME.findall(t), VARIATION_STOCK.findall(t)
    if names and stocks and names[0].startswith("豆") and "在庫なし" in stocks[0]:
        sold_out = True   # 豆のバリエーションが品切れ(粉のみ在庫あり)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    origin_label = field(desc, r"生産地(?=[\s：:])", r"農園名|標高|等級|収穫時期|品種|乾燥方法|精選方法|スクリーン|特徴|SCAA")
    c = detect_country_name(origin_label) if origin_label else None
    if c:
        parsed["origin_country"], parsed["origin_source"] = c, "product_description"
    parsed = apply_category_hint_fallback(parsed, name)
    proc = field(desc, "(?:精選方法|精製方法)", r"SCAA|$") or field(desc, "精選方法", r"SCAA|$")
    if proc and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(proc)

    roast_hint = None
    roast_level = None
    rm = re.match(r"^[☆★]?\s*(深煎り|中深煎り|中煎り|浅煎り)\s*[\(（]([^)）]*)[\)）]", desc)
    if rm:
        roast_hint = f"{rm.group(1)} ({rm.group(2)})"
        if "フルシティ" in rm.group(2):
            roast_level = "フルシティロースト"
    farm_parts = []
    for key, label in (("農園名", "農園"), ("標高", "標高"), ("品種", "品種")):
        v = field(desc, key, r"等級|収穫時期|品種|乾燥方法|精選方法|スクリーン|SCAA|特徴|標高|$")
        if v:
            farm_parts.append(f"{label}: {v}")
    farm_parts.insert(0, f"生産地: {origin_label}") if origin_label else None

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
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": re.split(r"生産地(?=[\s：:])", desc)[0][:400] or None,
        "blend_components": [],
        "decaf_process": None,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            rec = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if rec:
            records.append(rec)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_birdbethere.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_birdbethere.json に出力しました")


if __name__ == "__main__":
    main()
