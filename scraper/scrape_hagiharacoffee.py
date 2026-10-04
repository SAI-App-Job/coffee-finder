# -*- coding: utf-8 -*-
"""
scrape_hagiharacoffee.py

萩原珈琲(shop.hagihara-coffee.com、兵庫県神戸市灘区城内通1-6-18 の本社ビル1階
「COFFEE STUDIO」が本店。神戸・大阪の計7店舗)の商品情報を取得する。独自カート
(Vue.js製SPA + JSON API)。

【取得方法】
実データ確認済み(2026-10時点): 商品一覧は `/api/goods.json` が全145件を一括で返す
(商品ページはJSで描画されるため、HTMLスクレイピングは不要)。SSL証明書の検証を通した
状態でも取得できることを確認済み。
商品詳細ページのURLは `coffee_detail.html?id=<id>`(商品ごとに一意)。

【対象商品について】
大分類(fcategory)が「コーヒー豆」かつ goods_type が 0(通常の焙煎豆商品。ドリップ
バッグ=4、リキッド=3、ギフト・お試しセット=2等は別の値)の39件(ストレート17+ブレンド22)を対象とする。公開中
(disp_flag=1、del_flag=0)のもののみ。
ドリップバッグ・水出し・リキッド・ギフト・セット・紅茶・器具は対象外。
重量は capacity_text(100g、有機栽培珈琲のみ200g)。

【価格・在庫について】
商品詳細ページに「価格(税込)」と表示されており、APIのpriceは税込。在庫は
stock_flag(0=販売中、1=入荷待ち、2=欠品中、3=その他の販売停止コメント)で、0以外を
販売停止(完売扱い)とする。

【産地・焙煎度について】
introduce1(産地)が単一の国名のものはストレート扱いとして産地を取得する
(「令和8年10月限定珈琲 パプアニューギニア ワペナマンダ」はカテゴリ上ブレンド
だが単一産地のためストレート扱い)。複数産地(「エチオピア・ブラジル・その他」等)は
ブレンドとし産地は設定しない。introduce1の「ブラシル」(カフェインレスコーヒー)は
誤記と判断し「ブラジル」として扱う。焙煎度は商品名の「浅煎り/中煎り/深煎り/極深」を
roast_hintとして保持する(プロ向け8段階表記ではないためroast_levelは名称中の
キーワードがある場合のみ)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "萩原珈琲",
    "url": "https://shop.hagihara-coffee.com/",
    "platform": "独自カート(Vue.js + JSON API)",
    "address": "兵庫県神戸市灘区城内通1-6-18",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://shop.hagihara-coffee.com"
API_URL = f"{BASE_URL}/api/goods.json"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORY = "コーヒー豆"
EXCLUDE_KEYWORDS = ["ドリップバッグ", "リキッド", "ギフト", "セット", "水出し"]
ROAST_HINT_PATTERN = re.compile(r"(極深|深煎り|中煎り|浅煎り)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_goods() -> list[dict]:
    resp = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def clean_html_text(raw: str) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw.replace("\r\n", "\n"), "html.parser")
    for el in soup.select("span.link-high-light"):
        el.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def build_record(g: dict) -> dict | None:
    if (g.get("fcategory") or {}).get("title") != BEAN_CATEGORY:
        return None
    if g.get("goods_type") != "0" or g.get("disp_flag") != "1" or g.get("del_flag") != "0":
        return None
    name = re.sub(r"\s+", " ", g["goods_name"].replace("　", " ")).strip()
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    m = WEIGHT_PATTERN.search(g.get("capacity_text") or "")
    weight = int(m.group(1)) if m else None
    price = int(float(g["price"])) if g.get("price") else None

    scat = (g.get("scategory") or {}).get("title")
    origin_text = unicodedata.normalize("NFKC", g.get("introduce1") or "").replace("ブラシル", "ブラジル")
    multi_origin = bool(re.search(r"[・、,/]|他|その他", origin_text))
    single_origin = bool(origin_text) and not multi_origin and detect_country_name(origin_text) is not None
    is_blend = not (scat == "ストレート" or (single_origin and "ブレンド" not in name and "ミックス" not in name))

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(origin_text) if origin_text else None
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    mh = ROAST_HINT_PATTERN.search(name)
    roast_hint = mh.group(1) if mh else None

    desc = clean_html_text(g.get("introduce3") or "")[:400] or None
    available = g.get("stock_flag") == "0"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/coffee_detail.html?id={g['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for g in fetch_goods():
        rec = build_record(g)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hagiharacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hagiharacoffee.json に出力しました")


if __name__ == "__main__":
    main()
