# -*- coding: utf-8 -*-
"""
scrape_morrowcoffee.py

Morrow珈琲(福岡県小郡市横隈1664-10〈本店〉、morrow-coffee.com)の自社オンラインショップ(Shopify)の商品情報を取得する。
店舗は本店のほか Green Cafe Morrow(筑前町)、Little Morrow(筑後市)の計3店で、11店舗未満。

【実店舗・自家焙煎の根拠(2026-10-20確認)】
 - 公式サイト: 「自家焙煎した新鮮な珈琲豆の販売をはじめ、淹れたてのドリンクもご用意しています」、住所 〒838-0105 福岡県小郡市横隈1664-10。
 - 福岡クロスロード(crossroadfukuoka.jp/cycle/14406): 「自家焙煎の珈琲豆専門店Morrow珈琲」「飲みやすさと鮮度にこだわった自家焙煎コーヒーのお店」。

【楽天市場店を採用しなかった理由】
楽天(www.rakuten.co.jp/morrowcoffee/)はギフト中心のため、品目が揃う自社Shopifyを採用。

【価格改定について】
公式ニュースに「2026年10月20日より自社オンラインショップ珈琲豆価格改定」(10/11告知。金額の記載なし、理由は原材料費・仕入価格等の変動)。
取得は2026-10-20で、products.jsonの全商品のupdated_atが2026-10-20のため、改定後の価格の可能性が高い(確証なし)。

【対象商品について】
/products.json の豆25商品のうち、ドリップバッグのギフト・アソート(2件)と、ブレンドか単一産地か判別できない「秋のひととき」を除く。
各商品の「豆のまま」の最小重量(100g)の価格を代表とする。焙煎度は商品説明冒頭の「深煎り」等の記載がある場合のみ。
「期間限定20％OFF」の2商品(ウエウエテナンゴ)の表示価格は商品JSONの値(810円)をそのまま採用した。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "Morrow珈琲",
    "url": "https://morrow-coffee.com/",
    "platform": "Shopify",
    "address": "福岡県小郡市横隈1664-10",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。User-agent: * で Allow: /。/products.json を使用)",
    "source_note": "公式Shopify(https://morrow-coffee.com/)の/products.jsonを2026-10-20に取得。住所は公式トップと福岡クロスロードの記載。"
                   "2026-10-20に豆価格改定の告知あり(金額記載なし)で、取得価格は改定後の可能性が高い",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://morrow-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

EXCLUDE_HANDLES = {
    "ドリップバッグギフトセット-15個入", "アソートドリップバッグ20個入り",
    "期間限定20-off-秋のひととき",  # ブレンドか単一産地か説明文から判別できない
}
# handle -> 産地(ブレンドは対象外。商品名・説明文・アソートドリップの説明に産地記載があるもの)
ORIGINS = {
    "マチュピチュ-ペルー": "ペルー",
    "期間限定20-off-ウエウエテナンゴ-ファンシー": "グアテマラ",
    "アロマショコラ": "ブラジル",  # アソートドリップバッグ商品説明の「アロマショコラ【ブラジル】」
    "ピンクブルボン-コロンビア": "コロンビア",
    "エチオピア-ジナブ農園-g-3ナチュラル-ゲイシャ": "エチオピア",
    "ブラジル-キャラメラード": "ブラジル",
    "ブルーマウンテンno-1": "ジャマイカ",
    "デカフェ": "コロンビア",  # 説明文「コロンビアデカフェ」
    "モカクイーン": "エチオピア",
    "イルガチェフェ": "エチオピア",
    "ポパヤン": "コロンビア",  # 説明文「コロンビア ポパヤンGSP」
    "サンマリノ-樹上完熟": "ブラジル",  # 説明文「ブラジルの貴公子“サンマリノ”」
    "マンデリン": "インドネシア",
    "アンティグア": "グアテマラ",
    "タンザニアaa": "タンザニア",
    "シダモ": "エチオピア",
}
ROAST_PATTERN = re.compile(r"^\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def scrape_all_products():
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    records = []
    for p in resp.json()["products"]:
        if p["handle"] in EXCLUDE_HANDLES:
            continue
        title = re.sub(r"^【期間限定[^】]*】\s*", "", re.sub(r"\s+", " ", p["title"])).strip()
        beans = []
        for v in p["variants"]:
            opt = (v.get("option1") or "")
            m = WEIGHT_PATTERN.search(v.get("option2") or v.get("title") or "")
            if "豆" in opt and m:
                beans.append((int(m.group(1)), v))
        if not beans:
            continue
        weight, variant = min(beans, key=lambda x: x[0])
        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", re.sub(r"^期間限定\s*20％OFF\s*", "", body))
        rm = ROAST_PATTERN.match(body)
        roast = rm.group(1) if rm else None
        blend = "ブレンド" in title
        parsed = parse_product(title)
        if blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
            parsed["origin_country"] = ORIGINS.get(p["handle"])
            parsed["origin_source"] = "raw_name" if parsed["origin_country"] and parsed["origin_country"] in title else "description"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,  # 商品名の「ハイ」等の誤検出を避け、説明文冒頭の表記のみ使う
            "roast_hint": None,
            "flavor_notes": body[:400] or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if variant.get("available") else "完売",
            "out_of_stock": not variant.get("available"),
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_morrowcoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_morrowcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
