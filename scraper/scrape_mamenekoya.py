# -*- coding: utf-8 -*-
"""
scrape_mamenekoya.py

豆猫舎(mamenekoya.shop-pro.jp、千葉県佐倉市宮前2-11-7、「自家焙煎珈琲 豆猫舎」、
特定商取引法表記の販売業者は板垣陽子)の商品情報を取得する。
カラーミーショップ(charset=euc-jpのため`r.encoding = "euc-jp"`を明示する)。

【店舗発見の経緯】
千葉県の自家焙煎店調査(カラーミーショップ系)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全商品検索(?mode=srh&cid=&keyword=)で6件
(豆猫舎ブレンド・アンティークブレンド・コロンビア・グアテマラ・ブラジル・エチオピア)。
全商品が「珈琲豆」カテゴリの1袋200g入りで、ドリップバッグ・ギフトセット等の別形態は
存在しないため除外処理は不要。価格は税込(商品詳細のColorme JSON
product.sales_price_including_tax、簡易包装・豆のままの価格)を使う。
在庫は商品ページ本文の「SOLD OUT」表記(在庫0)で判定する
(2026-10時点でグアテマラとブラジルが売切れ)。
重量は商品ページ本文の「１袋　２００ｇ入」から取得する(全角を正規化)。
焙煎度は「中〜中深煎り」のような商品説明中の記述をroast_hintとして保持する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "豆猫舎",
    "url": "https://mamenekoya.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "千葉県佐倉市宮前2-11-7",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://mamenekoya.shop-pro.jp"
LIST_URL = f"{BASE_URL}/?mode=srh&cid=&keyword="
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップバッグ", "ドリップバック", "セット", "ギフト", "コーヒーバッグ")

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\s*入")
ROAST_PATTERN = re.compile(r"((?:浅|中浅|中|中深|深)(?:[〜~\-]\s*(?:浅|中浅|中|中深|深))?煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_product_ids() -> list[str]:
    html_text = fetch(LIST_URL)
    return list(dict.fromkeys(re.findall(r"\?pid=(\d+)", html_text)))


def build_record(pid: str) -> dict | None:
    html_text = fetch(f"{BASE_URL}/?pid={pid}")
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    name = unicodedata.normalize("NFKC", product.get("name") or "").strip()
    if not name or any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None

    body = BeautifulSoup(html_text, "html.parser").get_text("\n", strip=True)
    body_n = unicodedata.normalize("NFKC", body)

    weight_m = WEIGHT_PATTERN.search(body_n)
    weight_g = int(weight_m.group(1)) if weight_m else None
    roast_m = ROAST_PATTERN.search(body_n)
    roast_hint = roast_m.group(1) if roast_m else None

    # 商品説明(商品名の直後から「オプションの値段詳細」まで)
    desc = None
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    norm_lines = [unicodedata.normalize("NFKC", ln) for ln in lines]
    end = next((i for i, ln in enumerate(lines) if ln.startswith("オプションの")), len(lines))
    starts = [i for i in range(end) if norm_lines[i] == name]
    if starts:
        desc_lines = [ln for ln in lines[starts[-1] + 1:end]
                      if not re.match(r"^[0-9０-９]+袋", ln) and not re.match(r"^[0-9０-９]+[gｇ]", ln)]
        desc = " ".join(desc_lines).strip() or None

    stock_num = product.get("stock_num")
    sold_out = (stock_num == 0) if stock_num is not None else ("SOLD OUT" in body_n.upper())

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
        "roast_hint": roast_hint,
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
    records = []
    for pid in list_product_ids():
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
    with open("data_mamenekoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamenekoya.json に出力しました")


if __name__ == "__main__":
    main()
