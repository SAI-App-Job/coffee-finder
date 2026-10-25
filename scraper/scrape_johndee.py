# -*- coding: utf-8 -*-
"""
scrape_johndee.py

JOHN DEE COFFEE ROASTERS(ジョンディコーヒーロースターズ、神奈川県茅ヶ崎市美住町1-24 1階。
オンラインショップ john-dee.net、WordPress + WooCommerce)の自家焙煎コーヒー豆を取得する。
WooCommerce Store API(/wp-json/wc/store/v1/products)を使う。

【対象】全商品12件(カテゴリ「コーヒー豆」のみ。シロップ等の他カテゴリ商品は現時点でAPIに無い)。
【重量・価格】各商品は「グラム数(150g/200g/300g)」「焙煎指定」「挽き指定(豆のまま/細挽き/中挽き/粗挽き)」の
バリエーション。最小重量=150g の税込価格(Store APIのバリエーション価格。挽き指定で価格は変わらない)を採用。
100g のバリエーションは無い。
【焙煎度】購入時に焙煎指定(シナモン〜フルシティ、焙煎秒数)を選ぶ注文焙煎のため roast_level は None、
roast_hint に指定可能な範囲を記録する。
【産地等】short_description の「原産国：」「標高：」「精選：」「品種：」から取得。
【在庫】商品の is_in_stock(エルサルバトル ラス トレスSHG は在庫なし)。
"""

import html
import json
import re
import time

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "ジョンディコーヒーロースターズ (JOHN DEE)",
    "url": "https://john-dee.net/",
    "platform": "WordPress + WooCommerce",
    "address": "神奈川県茅ヶ崎市美住町1-24 1階",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。add-to-cart・wc-logs・wp-admin のみ禁止。Store APIは禁止対象外)",
    "source_note": "WooCommerce Store API(https://john-dee.net/wp-json/wc/store/v1/products)の12商品を2026-10-21に確認。"
                   "公式トップに店舗住所「神奈川県茅ヶ崎市美住町1-24 1階」、「JET ROASTER 熱風式焙煎機で3分程で焙煎します」と記載。"
                   "最小重量は150g(100gなし)。焙煎度は購入時に秒数で指定する注文焙煎。",
    "last_verified_at": "2026-10-21",
}

API_URL = "https://john-dee.net/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
LABEL_RE = re.compile(r"(原産国|標高|精選|品種|農園|地域)\s*[：:]\s*([^\n]+)")


def fetch_json(params):
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_products():
    products, page = [], 1
    while True:
        batch = fetch_json({"per_page": 100, "page": page})
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(DELAY)
    return products


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def attr_terms(p, name):
    for a in p.get("attributes", []):
        if a["name"] == name:
            return [t["name"] for t in a["terms"]]
    return []


def min_weight_price(p):
    """最小 グラム数 バリエーションの (重量g, 税込価格)。"""
    best = None
    for v in p.get("variations", []):
        for a in v["attributes"]:
            if a["name"] == "グラム数" and a["value"]:
                g = int(re.sub(r"\D", "", a["value"]))
                if best is None or g < best[0]:
                    best = (g, v["id"])
    if not best:
        return None, None
    time.sleep(DELAY)
    vars_ = fetch_json({"type": "variation", "parent": p["id"], "per_page": 100})
    for v in vars_:
        if v["id"] == best[1]:
            return best[0], int(v["prices"]["price"])
    return best[0], int(p["prices"]["price"])


def build(p):
    name = html.unescape(p["name"]).strip()
    weight, price = min_weight_price(p)
    if weight is None:
        return None
    short = strip_html(p.get("short_description"))
    labels = {k: v.strip() for k, v in LABEL_RE.findall(short)}
    desc_full = re.sub(r"\n\s*\n+", "\n", strip_html(p.get("description"))).strip()
    # 説明文のうち数値スケール(甘味 20% など)を除く
    desc_lines = [l.strip() for l in desc_full.split("\n") if l.strip() and not re.fullmatch(r"\d+%", l.strip())
                  and l.strip() not in ("甘味", "コク・深味", "酸味", "果実感", "苦味", "香り")]
    desc = " ".join(desc_lines)[:300] or None

    is_blend = "ブレンド" in name
    # サイト側の表記ゆれ「エルサルバトル」(正しくはエルサルバドル)
    parsed = parse_product(name.replace("エルサルバトル", "エルサルバドル"))
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if labels.get("原産国"):
            c = detect_country_name(labels["原産国"].replace("エルサルバトル", "エルサルバドル"))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, name.replace("エルサルバトル", "エルサルバドル"))
        if labels.get("精選") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(labels["精選"])
    roasts = attr_terms(p, "焙煎指定")
    roast_hint = ("購入時に焙煎度を指定(" + "・".join(roasts) + ")") if roasts else None
    farm = "、".join(f"{k}: {labels[k]}" for k in ("標高", "品種", "農園", "地域") if labels.get(k)) or None
    out = not p.get("is_in_stock", True)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": p.get("permalink"),
    }


def main():
    products = fetch_products()
    print(f"[info] API商品 {len(products)}件")
    records = []
    for p in products:
        cats = [c["name"] for c in p.get("categories", [])]
        if "コーヒー豆" not in cats:
            print(f"[skip] {p['name']} {cats}")
            continue
        rec = build(p)
        if rec:
            records.append(rec)
    with open("data_johndee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_johndee.json に出力しました")


if __name__ == "__main__":
    main()
