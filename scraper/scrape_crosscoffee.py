# -*- coding: utf-8 -*-
"""
scrape_crosscoffee.py

CROSS珈琲豆店(cross-coffee-beans.jp、東京都大田区仲六郷2-18-11 雑色商店街通り、2022年開業の
自家焙煎珈琲豆店。別店舗としてCROSS珈琲館(カフェ)があり合計2拠点)の商品情報を取得する。
オンラインストア(/ec/、secure-cms.net基盤の独自EC、決済はSquare)。

【ページ構造について】
実データ確認済み(2026-10時点): 商品カタログ(/ec/catalog/1/商品一覧、/2/ストレート、
/3/ブレンド)のリンクから商品コード付きの商品ページ(/ec/catalog/<カテゴリ>/<商品コード>/)を
列挙し、各商品ページの「価格 / 焙煎 / 商品詳細(<原産国>)」「在庫切れ」表示から取得する。
同じ商品が複数カテゴリ配下に重複して現れるため商品コードで重複排除し、先に見つかった
URLを採用する。商品名は「(生豆250g)」付きで、価格・重量は生豆250g基準
(「商品に記載している重さは生豆の状態でのグラム数」)のため重量は250g。
「フレンチロースト300g×5袋」(卸用セット)は除外。ブレンドは詳細欄の<原産国>に複数国が
並ぶ(「コロンビア・ブラジル…」)ためcategory「ブレンド」・産地None。
店頭メニュー(BEANSページ)は焙煎後200g単位の別価格表のため使わず、オンライン価格を採用する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "CROSS珈琲豆店",
    "url": "https://cross-coffee-beans.jp/",
    "platform": "独自EC(secure-cms.net基盤)",
    "address": "東京都大田区仲六郷2-18-11",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(2026-09時点で制限の記述なしと確認済み)",
}

BASE_URL = "https://cross-coffee-beans.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

CATALOG_PAGES = ["/ec/catalog/1/", "/ec/catalog/2/", "/ec/catalog/3/"]
PRODUCT_LINK = re.compile(r"/ec/catalog/(\d+)/([A-Za-z]+\d+)/")
EXCLUDE_KEYWORDS = ("袋", "セット", "ギフト")
WEIGHT_PATTERN = re.compile(r"生豆\s*(\d+)\s*g")
PRICE_PATTERN = re.compile(r"価格\s*([\d,]+)円")


def fetch_soup(path: str) -> BeautifulSoup:
    resp = requests.get(BASE_URL + path, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_product_paths() -> dict[str, str]:
    """商品コード -> 商品ページパス(最初に見つかったもの)"""
    found: dict[str, str] = {}
    for page in CATALOG_PAGES:
        soup = fetch_soup(page)
        for a in soup.find_all("a", href=True):
            m = PRODUCT_LINK.search(a["href"])
            if m and m.group(2) not in found:
                found[m.group(2)] = f"/ec/catalog/{m.group(1)}/{m.group(2)}/"
    return found


def build_record(code: str, path: str) -> dict | None:
    soup = fetch_soup(path)
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    try:
        start = lines.index("商品カタログ") + 1
        end = next(i for i in range(start, len(lines)) if lines[i] == "商品カテゴリー")
    except (ValueError, StopIteration):
        return None
    body = lines[start:end]
    # 本文: [カテゴリ名, 商品名, 商品名, "価格", "2,300円", ...]
    name_idx = next((i for i, ln in enumerate(body) if ln == "価格"), None)
    if name_idx is None or name_idx < 1:
        return None
    full_name = unicodedata.normalize("NFKC", body[name_idx - 1])
    if any(kw in full_name for kw in EXCLUDE_KEYWORDS):
        return None
    text = "\n".join(body)

    weight_m = WEIGHT_PATTERN.search(full_name)
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*[(（]生豆\s*\d+\s*g[)）]\s*", "", full_name).strip()
    name = re.sub(r"\s+", " ", name)

    price_m = PRICE_PATTERN.search(text.replace("\n", ""))
    price = int(price_m.group(1).replace(",", "")) if price_m else None
    out_of_stock = "在庫切れ" in body

    roast = None
    if "焙煎" in body:
        roast = body[body.index("焙煎") + 1]
    detail_idx = body.index("商品詳細") if "商品詳細" in body else None
    detail = body[detail_idx + 1:] if detail_idx is not None else []
    desc_lines = [ln for ln in detail if not ln.startswith("＜原産国＞") and ln != "<原産国>"]
    origin_text = ""
    for i, ln in enumerate(detail):
        if "原産国" in ln:
            origin_text = unicodedata.normalize("NFKC", " ".join(detail[i + 1:i + 2]))
            desc_lines = [d for d in detail[:i]]
            break
    desc = " ".join(desc_lines).strip() or None

    countries = [c for c in re.split(r"[・,、/]", origin_text) if c.strip()]
    parsed = parse_product(name)
    if "ブレンド" in name or "エスプレッソ" in name or len(countries) > 1:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(name),
        "grade": None if parsed["category"] == "ブレンド" else parsed["grade"],  # 「No.1」等はブレンドの商品番号でグレードではない
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": BASE_URL + path,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code, path in list_product_paths().items():
        try:
            record = build_record(code, path)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {path} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_crosscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_crosscoffee.json に出力しました")


if __name__ == "__main__":
    main()
