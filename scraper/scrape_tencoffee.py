# -*- coding: utf-8 -*-
"""
scrape_tencoffee.py

点珈琲店(三重県名張市赤目町丈六532-1、公式 https://tencoffee.shopinfo.jp/ = www.tencoffeeten.com)の
商品情報を取得する。Ameba Ownd(決済はBASE)。

【取得方法】onlineショップ一覧(/pages/906736/page_201703201746)から /shopItems/<id> のリンクを集め、
各商品ページの window.INITIAL_STATE 内の title / detail / price / stock / variations を読む。
【価格について】一覧ページは旧価格(1,600円)が表示されたままだが、商品ページ(JSON)は2026年10月からの
値上げ後の新価格(1,900円)になっており、一覧の告知「2026年10月より珈琲豆の値上げ」と整合するため、
商品ページの新価格を採用する。
【除外】ドリップバッグ8個セット、テスト用の「a」(100円)。重量は detail の「200g」。全て 200g の豆
(豆のまま/粉にして の2択)。在庫は stock / variationStock が 0 のとき品切れ。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "点珈琲店",
    "url": "https://tencoffee.shopinfo.jp/",
    "platform": "Ameba Ownd(BASE決済)",
    "address": "三重県名張市赤目町丈六532-1",
    "prefecture": "三重県",
    "robots_txt_status": "未確認(Ameba Ownd標準構成)",
}

LIST_URL = "https://tencoffee.shopinfo.jp/pages/906736/page_201703201746"
ITEM_URL = "https://tencoffee.shopinfo.jp/shopItems/{}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

DETAIL_RE = re.compile(r"\[\s*([^/\]]+?)\s*/\s*([^/\]]+?)\s*/\s*(\d+)\s*g\s*\]")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def jstr(s: str) -> str:
    return json.loads('"' + s + '"')


def fetch_item(item_id):
    url = ITEM_URL.format(item_id)
    t = get(url)
    i = t.find('"detail":"')
    if i < 0:
        return None
    seg = t[max(0, i - 3000):i + 3000]
    title_m = re.findall(r'"title":"((?:[^"\\]|\\.)*)"', t[max(0, i - 3000):i])
    detail_m = re.search(r'"detail":"((?:[^"\\]|\\.)*)","price":(\d+),"stock":(\d+),"visible":(true|false)', seg[seg.find('"detail"'):])
    if not title_m or not detail_m:
        return None
    title = jstr(title_m[-1]).replace("　", " ").strip()
    title = re.sub(r"\s+", " ", title)
    detail = jstr(detail_m.group(1))
    price = int(detail_m.group(2))
    stock = int(detail_m.group(3))
    var_stocks = [int(x) for x in re.findall(r'"variationStock":(\d+)', seg)]
    in_stock = stock > 0 and (not var_stocks or any(v > 0 for v in var_stocks))
    return {"id": item_id, "url": url, "title": title, "detail": detail, "price": price, "in_stock": in_stock}


def build_record(it):
    dm = DETAIL_RE.search(it["detail"])
    if not dm:
        return None  # ドリップバッグ・テスト商品などコーヒー豆の体裁でないもの
    roast, kind, grams = dm.group(1).strip(), dm.group(2).strip(), int(dm.group(3))
    name = it["title"]
    is_blend = kind == "ブレンド"
    tagline = re.sub(r"\[.*?\]", "", it["detail"], flags=re.S)
    tagline = re.sub(r"[−－\-]", "", tagline)
    tagline = re.sub(r"\s+", " ", tagline).strip() or None
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        c = detect_country_name(name)
        if c and not parsed["origin_country"]:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": tagline,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": grams,
        "stock_status": "販売中" if it["in_stock"] else "完売",
        "out_of_stock": not it["in_stock"],
        "product_url": it["url"],
    }


def scrape_all_products():
    ids = []
    for m in re.finditer(r'/shopItems/(\d+)', get(LIST_URL)):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    records = []
    for item_id in ids:
        try:
            it = fetch_item(item_id)
        except requests.HTTPError:
            continue  # 404(非公開/削除商品)
        time.sleep(0.5)
        if not it:
            continue
        rec = build_record(it)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_tencoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tencoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], r["flavor_notes"])


if __name__ == "__main__":
    main()
