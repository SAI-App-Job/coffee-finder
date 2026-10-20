# -*- coding: utf-8 -*-
"""
scrape_coffeesyanoda.py

珈琲舎のだ(福岡市中央区大名2-10-1 シャンボール大名1階の大名本店ほか5店舗、
オンラインショップ noda.shop-pro.jp、カラーミーショップ)の自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「ブレンドコーヒー(csid=1)・ストレートコーヒー(csid=2)・
スペシャルティコーヒー(csid=3)・カフェインレスコーヒー(csid=4)」(cbid=2979017)。
除外: 「テスト」商品、「復刻のだブレンド100g＆復刻キャニスター」(ギフト)、
「のだの人気ブレンド2種/3種ギフト」(ギフトセット)。ドリップパック・水出し・
お試しセット・カフェオレベース・スイーツ類は対象カテゴリ外。
【文字コード】EUC-JP。商品名は先頭の【味わい・焙煎度】を含む。重量は商品名の末尾(200g)
またはバリエーション(100g/200g)から取得し、各銘柄は豆のまま×最小重量を代表とする。
在庫はvar Colorme の product.stock_num が0以下の場合に品切れ(None=無制限)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "珈琲舎のだ",
    "url": "https://noda.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県福岡市中央区大名2-10-1 シャンボール大名1階",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ noda.shop-pro.jp のブレンド・ストレート・スペシャルティ・カフェインレス各カテゴリと商品詳細を2026-10-20に確認。"
                   "公式サイト(https://www.coffee-sya-noda.com/)で大名本店の所在地を確認。2026-10-15に販売価格改定のお知らせあり。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://noda.shop-pro.jp/"
CATEGORY_URLS = [BASE_URL + f"?mode=cate&cbid=2979017&csid={c}" for c in (1, 2, 3, 4)]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
EXCLUDE = ["テスト", "キャニスター", "ギフト", "ドリップ", "お試し", "セット"]
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
WEIGHT_RE = re.compile(r"(\d+)\s*[gｇ]", re.I)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.content.decode("euc-jp", errors="replace"), "html.parser"), r.content.decode("euc-jp", errors="replace")


def list_products():
    items = {}
    for u in CATEGORY_URLS:
        soup, _ = fetch(u)
        for li in soup.select("li.c-product"):
            a = li.select_one("a")
            t = li.select_one(".c-product__ttl")
            if not a or not t:
                continue
            name = t.get_text(strip=True)
            if any(k in name for k in EXCLUDE):
                continue
            items.setdefault(a["href"], (name, "ブレンド" if u.endswith("csid=1") else "ストレート"))
        time.sleep(DELAY)
    return items


def weight_of(v, title):
    m = WEIGHT_RE.search(unicodedata.normalize("NFKC", v.get("option2_value") or ""))
    return int(m.group(1)) if m else None


def build(href, list_info):
    list_name, list_cat = list_info
    url = BASE_URL + href
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    title = unicodedata.normalize("NFKC", p["name"]).replace("　", " ").strip()
    title = re.sub(r"\s*\*\*.*$", "", title).strip()  # 「**人気No.1」の販促文言を除去
    variants = p.get("variants") or []
    whole = [v for v in variants if "豆" in (v.get("option1_value") or "")] or variants
    sized = [(weight_of(v, title), v) for v in whole]
    sized = [(w, v) for w, v in sized if w]
    if sized:
        w, v = min(sized, key=lambda x: x[0])
        price = v["option_price_including_tax"]
        weight = w
    else:
        tw = WEIGHT_RE.search(title)
        weight = int(tw.group(1)) if tw else None
        price = whole[0]["option_price_including_tax"] if whole else p["sales_price_including_tax"]

    body = soup.select_one("div.p-product-explain__body")
    for br in (body.find_all("br") if body else []):
        br.replace_with("\n")
    text = body.get_text() if body else ""
    text = text.split("REVIEW")[0]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    desc = " ".join(lines)[:300] if lines else None
    if desc and "�" in desc:  # EUC-JP拡張文字の文字化け箇所以降は切り捨てる
        desc = desc.split("�")[0].strip() or None
    labels = {}
    for l in lines:
        mm = re.match(r"(生産国|生産地|農園名|標高|品種|生産処理|精選方法)\s*[:：]\s*(.+)", l)
        if mm:
            labels[mm.group(1)] = mm.group(2).strip()

    # 商品名先頭の【...】は味わい+焙煎度の見出し
    bracket = re.match(r"【([^】]*)】", title)
    clean = re.sub(r"【[^】]*】", "", title).strip()
    name_for_parse = title
    parsed = parse_product(name_for_parse)
    if list_cat == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if labels.get("生産国"):
            c = detect_country_name(labels["生産国"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if not parsed["origin_country"]:
            c = detect_country_name(clean)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, clean)
        if not parsed["origin_country"] and desc:
            c = detect_country_name(desc)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if labels.get("生産処理"):
            parsed["processing_method"] = normalize_processing_method(labels["生産処理"])

    roast_hint = None
    if bracket:
        seg = bracket.group(1).split("・")[-1]
        if "煎り" in seg:
            roast_hint = seg
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    farm = "、".join(f"{k}: {v}" for k, v in labels.items() if k in ("生産地", "農園名", "標高", "品種")) or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": clean if clean else title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    items = list_products()
    print(f"[info] 対象候補 {len(items)}件")
    records = []
    for href, name in items.items():
        try:
            rec = build(href, name)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {href} ({e})")
            continue
        if rec:
            records.append(rec)
        time.sleep(DELAY)
    with open("data_coffeesyanoda.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeesyanoda.json に出力しました")


if __name__ == "__main__":
    main()
