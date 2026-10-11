# -*- coding: utf-8 -*-
"""
scrape_inokuchicoffee.py

井ノ口珈琲(inokuchi-coffee.jp、岐阜県岐阜市六条片田1丁目15-1)のオンラインショップの
商品情報を取得する。WordPress + WooCommerce。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【robots.txtについて】
2026-10-11確認: User-agent: *に対し wc-logs・woocommerce_uploads・add-to-cart・/wp-admin/ のみ
Disallow(admin-ajax.phpは許可)。公開Store API(/wp-json/wc/store/v1/products)は制限対象外。
過去にCI環境のIPからのアクセスがブロックされた経緯があるため、取得に失敗した場合は
リトライしたうえで例外として扱う(取得できない場合は前回データを維持する運用を想定)。

【対象商品について】
実データ確認済み(2026-10時点): Store APIの全28商品のうち、カテゴリ「ブレンド」(アイスコーヒーブレンド・
金(こがね)ブレンド・井ノ口イタリアンブレンド・井ノ口ライトブレンド・井ノ口ブレンド)と
「シングルオリジン」(エチオピア ホワイトナイル)の焙煎豆6商品が対象。
ドリップパック・リキッドアイス・ゼリー・カフェオレベース・うずらベーカリー(焼き菓子・トート)・
ギフトセットは除外。ヴィンテージバレル(ウイスキー/ワイン)は酒樽にコーヒー豆を入れて「香りを添加」した
フレーバー系(インフューズド相当)の商品でカテゴリも「井ノ口珈琲オリジナルギフト」のため除外。
全商品「内容量 100g」(商品ページの「内容量」欄)で、豆or粉のバリエーションで価格差はない。
焙煎度・精製方法・産地は商品ページの項目欄(焙煎度/精製方法/生産地域)から取る(ブレンドは記載なし)。
在庫はStore APIの is_in_stock を使う(品切れ中のブレンドも「完売」として収録)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "井ノ口珈琲",
    "url": "https://inokuchi-coffee.jp/",
    "platform": "WordPress(WooCommerce)",
    "address": "岐阜県岐阜市六条片田1丁目15-1",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-10確認。管理系パスとadd-to-cartのみDisallow。Store APIは制限対象外)",
}

BASE_URL = "https://inokuchi-coffee.jp"
API_URL = f"{BASE_URL}/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORIES = {"ブレンド", "シングルオリジン"}
TAG_RE = re.compile(r"<[^>]+>")
ROAST_WORD = re.compile(r"(極深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
LABELS = ("内容量", "生産地域", "品種", "生産高度", "精製方法", "サプライヤー", "焙煎度", "酸味", "フレーバー", "ボディ", "余韻")


def get_with_retry(url: str, **kwargs) -> requests.Response:
    last = None
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s or "")).strip()


def fetch_all() -> list[dict]:
    out, page = [], 1
    while True:
        b = get_with_retry(API_URL, params={"per_page": 100, "page": page}).json()
        if not b:
            break
        out.extend(b)
        if len(b) < 100:
            break
        page += 1
    return out


def page_fields(url: str) -> dict:
    """商品ページの「内容量」「焙煎度」「精製方法」「生産地域」等の項目欄を {ラベル: 値} で返す。"""
    r = get_with_retry(url)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    for x in soup(["script", "style", "nav", "header", "footer"]):
        x.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    fields = {}
    for i, ln in enumerate(lines):
        if ln in LABELS and ln not in fields and i + 1 < len(lines):
            fields[ln] = lines[i + 1]
    return fields


def build_record(p: dict) -> dict | None:
    cats = {c["name"] for c in p.get("categories", [])}
    if not (cats & BEAN_CATEGORIES):
        return None
    name = re.sub(r"\s+", " ", p["name"].replace("　", " ")).strip()
    fields = page_fields(p["permalink"])
    wm = re.search(r"(\d+)\s*g", fields.get("内容量", ""), re.I)
    weight = int(wm.group(1)) if wm else None

    parsed = parse_product(name)
    if "ブレンド" in cats or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["processing_method"]:
            parsed["processing_method"] = detect_processing_method(fields.get("精製方法", ""))

    roast = None
    if fields.get("焙煎度"):
        m = ROAST_WORD.search(fields["焙煎度"])
        roast = m.group(1) if m else None
    desc = strip_html(p.get("short_description") or p.get("description") or "")[:400] or None
    sold_out = not p.get("is_in_stock", True)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(p["prices"]["price"]) if p.get("prices", {}).get("price") else None,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": p.get("permalink"),
    }


def main():
    records = []
    for p in fetch_all():
        r = build_record(p)
        if r:
            records.append(r)
        time.sleep(1)
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_inokuchicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_inokuchicoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:30])


if __name__ == "__main__":
    main()
