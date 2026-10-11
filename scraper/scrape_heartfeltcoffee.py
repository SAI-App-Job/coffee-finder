# -*- coding: utf-8 -*-
"""
scrape_heartfeltcoffee.py

Heartfelt Coffee(heartfeltcof.base.ec、奈良県磯城郡田原本町宮森10-1)の焙煎豆を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-11): sitemap.xml の全5商品のうち、100gのブレンド3種
(オリジナル・こくまろ・ほろ苦)のみ。飲み比べセット(9g×5)とCOLD BREWバッグは除外。
注文後焙煎。住所は /law にBASE社の所在地が出るため、店舗側の住所は依頼元提供の情報
(公式サイト heartfeltcoffee.net は2026-10時点でDNS解決不可のため未再確認)。
"""
import html as _h
import json
import re

import requests

SHOP_INFO = {
    "name": "Heartfelt Coffee",
    "url": "https://heartfeltcof.base.ec/",
    "platform": "BASE",
    "address": "奈良県磯城郡田原本町宮森10-1",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}
BASE_URL = "https://heartfeltcof.base.ec"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 商品ID: 商品名(ブレンドの構成国は商品名の表記どおり)
ITEMS = {
    "83945637": "オリジナルブレンド(パナマ産、エチオピア産)",
    "84230955": "こくまろブレンド(メキシコ、ホンジュラス)",
    "84231052": "ほろ苦ブレンド(パナマ、エチオピア、ケニア)",
}
WEIGHT_G = 100
DESC_RE = re.compile(r'og:description" content="([^"]*)"')
PRICE_RE = re.compile(r'product:price:amount" content="(\d+)"')
PURCH_RE = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def scrape_all_products():
    records = []
    for item_id, name in ITEMS.items():
        r = requests.get(f"{BASE_URL}/items/{item_id}", headers=HEADERS, timeout=30)
        r.encoding = "utf-8"
        t = r.text
        dm = DESC_RE.search(t)
        desc = re.sub(r"\s+", " ", _h.unescape(dm.group(1))).strip()[:400] if dm else None
        pm = PRICE_RE.search(t)
        pu = PURCH_RE.search(t)
        sold_out = bool(pu) and pu.group(1) == "unpurchasable"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "ブレンド",
            "origin_country": None,
            "origin_source": None,
            "designated_brand": None,
            "processing_method": None,
            "grade": None,
            "roast_level": None,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": [],
            "blend_components": [],
            "price": int(pm.group(1)) if pm else None,
            "weight_g": WEIGHT_G,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/items/{item_id}",
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_heartfeltcoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_heartfeltcoffee.json に出力しました")


if __name__ == "__main__":
    main()
