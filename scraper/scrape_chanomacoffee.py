# -*- coding: utf-8 -*-
"""
scrape_chanomacoffee.py

焙煎喫茶 chanoma coffee(https://www.chanoma-coffee.com/、岩手県盛岡市永井19地割38-68)のネット販売の豆を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-11時点): 豆は商品ページ1つ(/product-page/beans100-courier = 焙煎豆100g・通常配送)の中に
「豆の種類を選ぶ(35種)」「焙煎具合を選ぶ」「豆or粉」のオプションがあり、ページ埋め込みJSON(productItems/options)に
全バリエーションの価格と在庫が入っている。豆の種類ごとの価格(100g)を1銘柄1件として出力する。
- 100gは「生豆時のグラム数」で、焙煎後は目減りする旨が商品説明にある。
- 200g/300g版・クリックポスト版(beans*-post)は同じ銘柄の別重量/別配送のため最小の100g通常配送を代表とし対象外。
- ドリップバッグ・ギフト・生豆・デカフェ10袋(decaf10-courier等)は取得しない。
- 焙煎度は購入者が選ぶ(おまかせ/シナモン〜フレンチ)ため roast は null。豆のまま(豆)を選べる。
- 豆の特徴表(PDF)は usrfiles.com の robots.txt が403のため取得していない。
"""

import json
import re
import time
import unicodedata
from urllib.parse import quote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎喫茶 chanoma coffee",
    "url": "https://www.chanoma-coffee.com/",
    "platform": "Wix(Wix Stores)",
    "address": "岩手県盛岡市永井19地割38-68",
    "prefecture": "岩手県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
    "source_note": "ネット販売の商品ページ https://www.chanoma-coffee.com/product-page/beans100-courier(焙煎豆100g・通常配送)の埋め込みJSON(商品オプション35種の価格・在庫)を2026-11-03に確認。"
                   "住所・店舗は公式トップ(SHOP INFO)による。豆の種類・焙煎具合・豆/粉を選ぶオーダー焙煎方式で、100gは生豆時の重量(焙煎後は目減り)。"
                   "ドリップバッグ・ギフト・生豆・200g/300g・クリックポスト版は除外。営業時間変更のお知らせ(2026-11-02付)が公式トップに掲載されており更新は新しい。",
    "last_verified_at": "2026-11-03",
}

PAGE_URL = "https://www.chanoma-coffee.com/product-page/beans100-courier"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2
PREFIX = re.compile(r"^(スペシャルティ|限定プレミアム)\s*[｜|]\s*")


def fetch_page() -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_variants(html_text: str):
    dec = json.JSONDecoder()
    i = html_text.find('"productItems":')
    items, _ = dec.raw_decode(html_text[i + len('"productItems":'):])
    n = html_text.find('"nextOptionsSelectionId"')
    o = html_text.find('"options":', n)
    opts, _ = dec.raw_decode(html_text[o + len('"options":'):])
    sel = {}
    for op in opts:
        for s in op["selections"]:
            sel[s["id"]] = (op["title"], s["value"])
    return items, sel


def main():
    items, sel = parse_variants(fetch_page())
    beans: dict[str, dict] = {}
    for it in items:
        if not it.get("isVisible", True):
            continue
        d = {sel[x][0]: sel[x][1] for x in it["optionsSelections"]}
        if d.get("豆or粉") != "豆":
            continue  # 豆のままの価格を採用
        bean = d["豆の種類を選ぶ"]
        in_stock = it["inventory"]["status"] == "in_stock"
        cur = beans.get(bean)
        # 同一銘柄は焙煎度違いでも同価格。1つでも購入可能なら販売中とする
        if cur is None:
            beans[bean] = {"price": int(it["price"]), "in_stock": in_stock}
        else:
            cur["in_stock"] = cur["in_stock"] or in_stock
            cur["price"] = min(cur["price"], int(it["price"]))

    records = []
    for bean, v in beans.items():
        full = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", bean)).strip()
        tier = PREFIX.match(bean)
        name = PREFIX.sub("", full if not tier else bean).strip()
        name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name)).strip()
        name = re.sub(r"(AGE of Novo)(?=\S)", r"\1 ", name)
        is_blend = "ぶれんど" in name
        is_decaf = name == "デカフェ"
        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "デカフェ" if is_decaf else "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(name)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": None,
            "roast_hint": None,
            "flavor_notes": None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": v["price"],
            "weight_g": 100,
            "stock_status": "販売中" if v["in_stock"] else "完売",
            "out_of_stock": not v["in_stock"],
            "product_url": PAGE_URL + "#" + quote(name),
        })

    output = {"shop": SHOP_INFO, "products": records}
    with open("data_chanomacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chanomacoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["processing_method"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
