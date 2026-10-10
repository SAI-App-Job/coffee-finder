# -*- coding: utf-8 -*-
"""
scrape_horicoffee.py

ホリ珈琲(1968年創業、三重県桑名市中央町2-11 本店ほか計5店舗、公式 https://hori-coffee.co.jp/)の
コーヒー豆通販の商品情報を取得する。ECは WordPress + Welcart(WooCommerceではない。
/wp-json/wc/store/v1 は404)。サイトは一部環境で403になることがあるため通常のUser-Agentを付ける。

【取得方法】post-sitemap.xml から商品ページ(Welcartの商品は投稿として公開)の全URLを集め、
各ページの h1 / 価格 / 「内容量」 / 「在庫状態」 / 説明文を読む。
【対象】内容量が「200g」の焙煎豆(ホリブレンドNo.18、アロマモカプリンセス、スウィートダークロースト、
ブルーマウンテンNO1、トミオ・フクダDOT、コスタリカ・ハニー、極上ブルマンブレンド、
デカフェオーガニック メキシコ)。ドリップバッグ/ドリップパック、アイスコーヒー(リキッド)、
各種セット・ギフト、定期便、プリン等スイーツは除外。
【店舗数】公式 /shop/ に 本店・焙煎所・四日市・アピタ松阪・アピタ桑名 の5店舗(焙煎所は直売併設)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ホリ珈琲",
    "url": "https://hori-coffee.co.jp/",
    "platform": "WordPress + Welcart",
    "address": "三重県桑名市中央町2-11",
    "prefecture": "三重県",
    "robots_txt_status": "未確認(WordPress標準構成)",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ja",
}
SITEMAP = "https://hori-coffee.co.jp/post-sitemap.xml"

EXCLUDE_WORDS = ["ドリップ", "セット", "ギフト", "定期", "アイス", "チーズケーキ", "メール便"]
BLEND_NAMES = ["ホリブレンド", "アロマモカ", "スウィートダーク", "ブルマンブレンド"]
ROAST_BY_SLUG = {
    "decafe": "中深煎り",                      # 「中深煎りのデカフェコーヒー」
    "sweet-dark-holider-roast": "深煎り",     # 「深煎り珈琲の決定版」
    "the-finest-bullman-blend": "深煎り",     # 「深煎りタイプのブルマンブレンド」
}
ROAST_RE = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def clean(s):
    return re.sub(r"\s+", " ", s.replace("　", " ").replace(" ", " ")).strip()


def parse_page(url):
    t = get(url)
    m = re.search(r"<title>([^<|]*)", t)
    title = clean(re.sub(r"&amp;", "&", m.group(1))) if m else None
    if not title:
        return None
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    txt = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", body))
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    wm = re.search(r"内容量\s*\n\s*(\d+)\s*g\s*\n", txt) or re.search(r"(\d+)\s*g$", title)
    if not wm:
        return None
    weight = int(wm.group(1))
    pm = re.search(r"¥\s*([\d,]+)", txt)
    price = int(pm.group(1).replace(",", "")) if pm else None
    sm = re.search(r"在庫状態\s*:\s*([^\n]+)", txt)
    stock_text = sm.group(1).strip() if sm else None
    # 価格行(円（税込）)の直後から「原材料」までの説明文
    desc = None
    lines = [l.strip() for l in txt.splitlines()]
    fixed = {"ご注文はこちら", "リンクをコピーして", "シェア"}
    for i, l in enumerate(lines):
        if l.startswith("円（税込）"):
            got = []
            for l2 in lines[i + 1:]:
                if l2.startswith("原材料") or (l2 == "ご注文はこちら" and got):
                    break
                if l2 in fixed or not l2:
                    continue
                got.append(l2)
            desc = clean(" ".join(got)) or None
            break
    return {"url": url, "title": title, "weight": weight, "price": price, "stock_text": stock_text, "desc": desc}


def build_record(p):
    name = p["title"]
    # 「200g」はタイトルに付くが商品名には不要なので除く
    name = clean(re.sub(r"\s*\d+g$", "", name))
    if any(w in name for w in EXCLUDE_WORDS) or re.search("プリン(?!セス)", name):
        return None
    is_blend = any(w in name for w in BLEND_NAMES) or "ブレンド" in name
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
    if not is_blend and not parsed["origin_country"] and p["desc"]:
        om = re.match(r"(\S{2,8}?)産", p["desc"])
        c = detect_country_name(om.group(1)) if om else None
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
    rm = ROAST_RE.search(name) or (ROAST_RE.search(p["desc"] or ""))
    roast = rm.group(1) if rm else parsed["roast_level"]
    # 商品ページ本文に焙煎度の記載がある商品(名称・説明文の先頭には出ない)
    roast = ROAST_BY_SLUG.get(p["url"].rstrip("/").rsplit("/", 1)[-1], roast)
    st = p["stock_text"] or ""
    in_stock = ("在庫有り" in st) or (st == "")
    if any(w in st for w in ["なし", "売り切れ", "売切", "品切", "完売"]):
        in_stock = False
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
        "flavor_notes": p["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": p["price"],
        "weight_g": p["weight"],
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["url"],
    }


def scrape_all_products():
    locs = re.findall(r"<loc>([^<]*)</loc>", get(SITEMAP))
    records = []
    for url in locs:
        try:
            p = parse_page(url)
        except requests.HTTPError:
            continue
        time.sleep(0.4)
        if not p:
            continue
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_horicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_horicoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
        print("     ", (r["flavor_notes"] or "")[:100])


if __name__ == "__main__":
    main()
