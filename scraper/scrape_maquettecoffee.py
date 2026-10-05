# -*- coding: utf-8 -*-
"""
scrape_maquettecoffee.py

MAQUETTE COFFEE SHOP(store-maquettecoffee.com、愛知県豊田市上野町3-26-1)の商品情報を
取得する。カラーミーショップ(文字コードEUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「COFFEES」(cbid=1970379、2ページ・計39件)のうち、
商品名に「/100g」「/200g」と重量が付く焙煎豆(シングルオリジン・ブレンド・デカフェ・季節ブレンド)と
「ALL PURPOSE BLEND」を対象とする。COFFEE BAG(ドリップバッグ)・COLD BREW・milk coffee conc.・
アート作品(玉山拓郎:FLOOR)は除外。GOODSカテゴリ(器具・雑貨)は対象外。
販売終了後も商品ページは残る運用で、在庫0(sold out)のロットが多い(約8割)ため、完売として収録する。
ALL PURPOSE BLENDは「シングル(200g×1)」と「ダブル(200g×2)」のバリエーションがあり、
最小のシングル(200g)を代表とする。

【ページ構造について】
商品ページ内の`var Colorme = {...}`に税込価格(sales_price_including_tax)があり、
在庫は購入ボタン(btn-addcart)の有無/「sold out」表示で判定する。説明文(div.product-order-exp)は
「生産国|…」「生産処理|…」「ロースト|…」「風味|…」の構造化書式。ブレンドは「ブレンド内容」節を持つ。
"""

import html as htmllib
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "MAQUETTE COFFEE SHOP",
    "url": "http://store-maquettecoffee.com/",
    "platform": "カラーミーショップ",
    "address": "愛知県豊田市上野町3-26-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "http://store-maquettecoffee.com"
CATEGORY_URL = BASE_URL + "/?mode=cate&csid=0&cbid=1970379&page={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 10

NAME_WEIGHT_PATTERN = re.compile(r"/\s*(\d+)\s*g\s*$", re.I)
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティー?|フレンチ|イタリアン|ダーク)ロースト")
COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        found = re.findall(r'href="\?pid=(\d+)"', fetch_html(CATEGORY_URL.format(page=page)))
        new = [p for p in dict.fromkeys(found) if p not in pids]
        if not new:
            break
        pids += new
    return pids


def parse_fields(text: str) -> dict:
    """「項目｜値」形式の行を辞書にする(最初に現れた値を採用)。"""
    fields = {}
    for line in text.split("\n"):
        m = re.match(r"^([^｜|\n]{1,12})[｜|]\s*(.+)$", line.strip())
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def flavor_text(text: str) -> str | None:
    """「風味」見出しの直後から、「生産国｜」「詳細」「ブレンド内容」の手前までを返す。"""
    lines = text.split("\n")
    out = []
    started = False
    for line in lines:
        s = line.strip()
        if not started:
            if s == "風味":
                started = True
            continue
        if re.match(r"^(生産国|生産地|詳細|ブレンド内容)", s):
            break
        out.append(s)
    return re.sub(r"\s+", " ", " ".join(out)).strip()[:400] or None


def build_record(pid: str) -> dict | None:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    name_el = soup.select_one(".product-name")
    if not name_el:
        return None
    raw = htmllib.unescape(re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))).strip()
    wm = NAME_WEIGHT_PATTERN.search(raw)
    is_all_purpose = raw.upper().startswith("ALL PURPOSE BLEND")
    if not wm and not is_all_purpose:
        return None  # ドリップバッグ・COLD BREW・雑貨等
    title = NAME_WEIGHT_PATTERN.sub("", raw).strip()
    title = re.sub(r"\s*\|\s*", " | ", title)

    colorme = COLORME_PATTERN.search(html_text)
    price = None
    if colorme:
        price = json.loads(colorme.group(1))["product"].get("sales_price_including_tax")

    weight_g = int(wm.group(1)) if wm else None
    if weight_g is None:
        spec = soup.select_one(".product-order-spec")
        sm = re.search(r"(\d+)\s*g", spec.get_text(" ", strip=True)) if spec else None
        weight_g = int(sm.group(1)) if sm else None

    order_input = soup.select_one(".product-order-input")
    sold_out = not (order_input and order_input.select_one("button.btn-addcart"))

    exp = soup.select_one(".product-order-exp")
    text = exp.get_text("\n", strip=True) if exp else ""
    fields = parse_fields(text)
    flavor_notes = flavor_text(text)

    is_blend = ("ブレンド内容" in text) or "BLEND" in raw.upper() or "FLAVOR" in raw.upper()
    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        country_text = fields.get("生産国")
        c = detect_country_name(country_text) if country_text else None
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    proc = fields.get("生産処理") or fields.get("生産処理方法")
    processing = normalize_processing_method(proc) if proc else (parsed["processing_method"] or detect_processing_method(title))

    if is_blend:
        processing = None  # ブレンドは複数ロットの混合のため単一の精選方法を持たない

    roast = fields.get("ロースト")
    if not roast:
        if "DARK ROAST" in raw.upper():
            roast = "ダークロースト"
        elif not is_blend or is_all_purpose:
            m = ROAST_PATTERN.search(flavor_notes or "")
            roast = m.group(0) if m else None
    if roast == "シティーロースト":
        roast = "シティロースト"

    decaf_process = None
    if re.search(r"DECAF|デカフェ|カフェインレス", title, re.I):
        if re.search(r"マウンテンウォーター", text):
            decaf_process = "マウンテンウォータープロセスによりカフェインを除去"
        elif re.search(r"スイスウォーター", text):
            decaf_process = "スイスウォータープロセスによりカフェインを除去"
        elif re.search(r"液体(?:CO2|二酸化炭素)|CO2", text):
            decaf_process = "液体CO2抽出によりカフェインを除去"
        elif re.search(r"エチルアセテート|シュガーケーン|サトウキビ由来", text):
            decaf_process = "エチルアセテート製法によりカフェインを除去"

    record = {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": fields.get("農園名") or fields.get("農園"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }
    if decaf_process:
        record["decaf_process"] = decaf_process
    return record


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_pids():
        try:
            rec = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_maquettecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_maquettecoffee.json に出力しました")


if __name__ == "__main__":
    main()
