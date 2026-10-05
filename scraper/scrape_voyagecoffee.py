# -*- coding: utf-8 -*-
"""
scrape_voyagecoffee.py

Voyage coffee & sundries(www.voyage-coffee.net、愛知県半田市栄町4-79、
実体はcoffee-voyage.shop-pro.jp)の商品情報を取得する。カラーミーショップ(文字コードEUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(cbid=1434906)の16件
(シングルオリジン10・ブレンド5・カフェインレス1)を対象とする。ドリップパック(1434907)・
セット(1454606)・定期便(1434920)・ギフト(1653562)・カフェオレベースは対象外。

【価格・重量について】
各商品は「豆のまま/ドリップ(中挽き)/フレンチプレス(中粗挽き)」×「100g/200g(10%OFF)/500g(20%OFF)」の
バリエーション(Colorme JSONのvariants、option2_valueが「940yen / 100g」形式)を持つ。
最小重量(100g)のバリエーションの税込価格を代表とする(挽き方による価格差は無い)。

【在庫について】
購入ボタン(button.cart_in_async)が無い商品を完売と判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "Voyage coffee & sundries",
    "url": "https://www.voyage-coffee.net/",
    "platform": "カラーミーショップ",
    "address": "愛知県半田市栄町4-79",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://www.voyage-coffee.net"
CATEGORY_ID = "1434906"  # コーヒー豆
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 10

COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\b", re.I)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        t = fetch_html(f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0&page={page}")
        new = [p for p in dict.fromkeys(re.findall(r"[?&]pid=(\d+)", t)) if p not in pids]
        if not new:
            break
        pids += new
    return pids


def pick_min_weight(variants: list[dict]) -> tuple[int | None, int | None]:
    cands = []
    for v in variants:
        wm = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        price = v.get("option_price_including_tax")
        if wm and price is not None:
            cands.append((int(wm.group(1)), int(price)))
    if not cands:
        return None, None
    return min(cands)


def parse_fields(text: str) -> dict:
    fields = {}
    for line in text.split("\n"):
        m = re.match(r"^\s*([^：:\n]{1,8}?)\s*[：:]\s*(.+)$", line)
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def build_record(pid: str) -> dict | None:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    m = COLORME_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1))["product"]
    title = re.sub(r"\s+", " ", product["name"].replace("　", " ")).strip()
    weight_g, price = pick_min_weight(product.get("variants") or [])
    if price is None:
        price = product.get("sales_price_including_tax")

    soup = BeautifulSoup(html_text, "html.parser")
    sold_out = soup.select_one("button.cart_in_async") is None
    short_el = soup.select_one(".p-short-description")
    body_el = soup.select_one(".p-product-body__description")
    body_text = body_el.get_text("\n", strip=True) if body_el else ""
    fields = parse_fields(body_text)
    body_main = re.split(r"\n生産国", body_text)[0]
    flavor = " ".join(x for x in [short_el.get_text(" ", strip=True) if short_el else "", body_main] if x)
    flavor = re.sub(r"\s+", " ", flavor).strip()[:400] or None

    is_blend = "ブレンド" in title
    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(fields.get("生産国") or "")
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        # 「タイ」はcoffee_parserの国名辞書が誤爆回避のため対象外にしている。説明文の「生産国：タイ」を直接採用する
        if not parsed["origin_country"] and (fields.get("生産国") or "").strip() == "タイ":
            parsed["origin_country"] = "タイ"
            parsed["origin_source"] = "description"

    proc = fields.get("生産処理") or fields.get("精製方法") or fields.get("精製")
    if is_blend:
        processing = None
    elif proc:
        processing = normalize_processing_method(proc)
    else:
        processing = parsed["processing_method"] or detect_processing_method(title)

    rm = ROAST_PATTERN.search(title)
    roast = rm.group(1) if rm else None
    farm = fields.get("農園") or fields.get("農園名") or fields.get("精製所")

    return {
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
        "flavor_notes": flavor,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


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
    with open("data_voyagecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_voyagecoffee.json に出力しました")


if __name__ == "__main__":
    main()
