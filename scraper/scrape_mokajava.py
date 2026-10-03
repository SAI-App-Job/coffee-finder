# -*- coding: utf-8 -*-
"""
scrape_mokajava.py

モカジャバ(有限会社モカジャバコーヒーロースター、mokajava.co.jp、東京都世田谷区南烏山6-27-9
グレースYK101、千歳烏山店のほか多摩焙煎アトリエを持つ自家焙煎店・計2〜3拠点)の商品情報を
取得する。ショップサーブ(ShopServe、UTF-8)。

【対象商品について】
実データ確認済み(2026-10時点): 「モカジャバのコーヒー豆 一覧表」(/SHOP/61512/list.html、
全23件・1ページ)のうち、複数袋の「セット」商品(まかないコーヒーセット200g×9袋・
ハウスブレンドセット500g×2袋・深煎りブレンドセット500g×4袋)とドリッパー(CAFEC)を除く19件
(ストレート・ブレンド)を収録する。ギフトセット・ドリップバッグ・アイスコーヒー
ボトル・ドリッパー等の器具、およびふるさと納税(さとふる)の返礼品は別カテゴリのため対象外。

【重量・価格・在庫】
各商品詳細ページの「内容量／価格／在庫」表(200g・500g)から最小サイズ(200g)の行を採用する
(一覧の「¥1,170 〜」は最小サイズ価格と一致)。在庫は表の記号(○=あり、×=なし)で判定する
(「ブラジル・モンテアレグレ農園」は×=完売)。商品ページには説明文がテキストで無い
(画像のみ)ためflavor_notesは取得できず、焙煎度は一覧のカテゴリ(中浅煎〜極深煎)から
roast_hintとして採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "モカジャバ",
    "url": "https://www.mokajava.co.jp/",
    "platform": "ショップサーブ",
    "address": "東京都世田谷区南烏山6-27-9 グレースYK101",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.mokajava.co.jp"
LIST_URL = f"{BASE_URL}/SHOP/61512/list.html"
ROAST_CATEGORIES = {
    "中浅煎": "1168704",
    "中煎": "1168705",
    "中深煎": "1168706",
    "深煎": "1168707",
    "極深煎": "1168708",
}
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップ", "ボトル", "ふるさと", "ドリッパー", "CAFEC")
SIZE_ROW = re.compile(r"(\d+)\s*g\s*(?:[^\d¥(]{0,30}?\s)?¥\s*([\d,]+)\s*\(税込\)\s*([○×△◎]?)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items(url: str) -> list[dict]:
    soup = BeautifulSoup(fetch(url), "html.parser")
    items = []
    for sec in soup.select("section.column4"):
        a = sec.select_one("h2 a")
        if not a:
            continue
        items.append({
            "name": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
            "path": a["href"],
        })
    return items


def roast_hints() -> dict[str, str]:
    """焙煎度カテゴリのリストから {商品パス: 焙煎度ラベル} を作る。"""
    hints: dict[str, str] = {}
    for label, cid in ROAST_CATEGORIES.items():
        try:
            for item in list_items(f"{BASE_URL}/SHOP/{cid}/list.html"):
                hints.setdefault(item["path"], label)
        except requests.RequestException as e:
            print(f"[warn] 焙煎度カテゴリ取得失敗: {label} ({e})")
    return hints


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    text = " ".join(ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip())
    rows = [(int(w), int(p.replace(",", "")), mark) for w, p, mark in SIZE_ROW.findall(text)]
    if not rows:
        return {"weight_g": None, "price": None, "out_of_stock": False}
    w, p, mark = min(rows, key=lambda r: r[0])
    return {"weight_g": w, "price": p, "out_of_stock": mark == "×"}


def build_record(item: dict, detail: dict, roast_label: str | None) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    display = re.sub(r"^【[^】]*】", "", name).strip().replace("“", "").replace("”", "")
    parsed = parse_product(display)
    if parsed["category"] == "ブレンド" or "ブレンド" in display or "モカジャバフレンチ" in display:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, display)
    out = detail["out_of_stock"]
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
        "roast_hint": roast_label,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": BASE_URL + item["path"] if item["path"].startswith("/") else item["path"],
    }


NON_BEAN_KEYWORDS = EXCLUDE_KEYWORDS


def scrape_all_products() -> list[dict]:
    hints = roast_hints()
    records = []
    for item in list_items(LIST_URL):
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(BASE_URL + item["path"]))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['path']} ({e})")
            continue
        rec = build_record(item, detail, hints.get(item["path"]))
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mokajava.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mokajava.json に出力しました")


if __name__ == "__main__":
    main()
