# -*- coding: utf-8 -*-
"""
scrape_coffeetamazawa.py

珈琲玉澤(coffee-tamazawa.shop、千葉県香取市佐原イ3401、2019年開業の自家焙煎珈琲店、
運営は株式会社玉澤商会)の商品情報を取得する。カラーミーショップ
(charset=euc-jpのため`r.encoding = "euc-jp"`を明示する)。

【店舗発見の経緯】
千葉県の自家焙煎店調査(カラーミーショップ系)で発見。トップページに豆3種のみが並んで
いたが、「コーヒー豆」カテゴリ(cbid=2767142)は全13件あることを確認した。

【対象商品について】
実データ確認済み(2026-10時点): 「コーヒー豆」カテゴリ13件のうち、
「テイスティングセット (100g x 4)」(複数銘柄のセット)を除く12件(ブレンド4・
ストレート7・デカフェ1)を収録する。他カテゴリ(その他のコーヒー=ドリップバッグ・
水出しバッグ、器具、雑貨、ギフトセット)は対象外。
全商品が200g入りの単一サイズ(挽き方のみ選択、価格は同一)で、価格は税込。
商品名は「ブラジル 200g |【合計400g以上で送料無料】」のように重量・送料注記が
付くため、「|」以降と重量表記を除いた名前をraw_nameとし、重量は名前の「200g」から取る。
焙煎度は「★★★☆☆」の相対評価のみでroast_levelは取れない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲玉澤",
    "url": "https://coffee-tamazawa.shop/",
    "platform": "カラーミーショップ",
    "address": "千葉県香取市佐原イ3401",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://coffee-tamazawa.shop"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2767142&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ドリップバッグ", "ドリップバック", "ギフト", "バッグ")

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def build_record(pid: str) -> dict | None:
    html_text = fetch(f"{BASE_URL}/?pid={pid}")
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None

    head = title.split("|")[0].strip()
    weight_m = WEIGHT_PATTERN.search(head)
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*\d+\s*g\s*", " ", head, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()

    # 説明文(商品名行〜「香り ★…」の評価行の手前)
    lines = [ln.strip() for ln in BeautifulSoup(html_text, "html.parser").get_text("\n", strip=True).split("\n") if ln.strip()]
    desc = None
    starts = [i for i, ln in enumerate(lines) if ln == title]
    if starts:
        desc_lines = []
        for ln in lines[starts[0] + 1:]:
            if ln.startswith("香り") or ln.startswith("*"):
                break
            desc_lines.append(ln)
        desc = " ".join(desc_lines).strip() or None
    body_text = "\n".join(lines)
    sold_out = product.get("stock_num") == 0 or "SOLD OUT" in body_text.upper()

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
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
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    pids = list(dict.fromkeys(re.findall(r"\?pid=(\d+)", fetch(CATEGORY_URL))))
    records = []
    for pid in pids:
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeetamazawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeetamazawa.json に出力しました")


if __name__ == "__main__":
    main()
