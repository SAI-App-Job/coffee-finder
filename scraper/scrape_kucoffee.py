# -*- coding: utf-8 -*-
"""
scrape_kucoffee.py

ku.(コーヒー豆と器のお店、千葉県千葉市稲毛区小仲台2-13-13、ku-plus-f.com)の商品情報を取得する。
「自家焙煎スペシャルティコーヒー豆」と作家の器・雑貨・アクセサリーを扱う店舗で、店舗は1店のみ。
EC-CUBE製のネットショップ。

【対象商品について】
実データ確認済み(2026-10時点、サイト内の掲載はコーヒー豆カテゴリ category_id=140 の4銘柄):
コスタリカ・コロンビア・エクアドル・東ティモールのストレート各100g(¥972 税込)。
器・雑貨・アクセサリー・Tシャツ等は対象外。トップページに載っていたグアテマラ(ID 4329)は
詳細ページが404(掲載終了)のため含まない。ブレンドの掲載は無し。

【価格・重量・焙煎度について】
商品名の末尾「100g」がそのまま内容量で、一覧の税込価格を採用。各詳細ページに
「基本的に中煎りでお届けします。焙煎度にご指定がある場合はお知らせください」とあるため
roast_levelは中煎り、roast_hintにその旨を保持する(別途【焙煎度】欄の記載は参考値)。
産地・標高・品種・精製・フレーバーノートは詳細ページの【】欄から farm_note / flavor_notes に保持する。
在庫は一覧の「カートに入れる」ボタンの有無で判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ku.(コーヒー豆と器のお店)",
    "url": "https://ku-plus-f.com/",
    "platform": "EC-CUBE",
    "address": "千葉県千葉市稲毛区小仲台2-13-13",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

LIST_URL = "https://ku-plus-f.com/products/list?category_id=140"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
FIELD_RE = re.compile(r"^【\s*([^】]+?)\s*】\s*(.*)$")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def parse_detail(url: str) -> dict:
    soup = fetch(url)
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n")]
    fields: dict[str, str] = {}
    for ln in lines:
        m = FIELD_RE.match(ln)
        if m:
            key = re.sub(r"\s+", "", m.group(1))
            fields.setdefault(key, m.group(2).strip())
    return fields


def scrape_all_products() -> list[dict]:
    soup = fetch(LIST_URL)
    records = []
    for li in soup.select("li.ec-shelfGrid__item"):
        a = li.find("a", href=True)
        if not a:
            continue
        title = re.sub(r"\s+", " ", a.select("p")[-2].get_text(strip=True) if len(a.select("p")) > 1 else a.get_text(strip=True))
        price_el = li.select_one("p.price02-default")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        if not pm:
            continue
        wm = re.search(r"(\d+)\s*g\s*$", title)
        name = re.sub(r"[\s　]*\d+\s*g\s*$", "", title).strip()
        name = re.sub(r"[\s　]+", " ", name)
        in_stock = li.select_one("button.add-cart") is not None
        url = a["href"]

        fields = parse_detail(url)
        parsed = parse_product(name)
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name.split(" ")[0])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

        farm_parts = [f"{k}: {fields[k]}" for k in ("標高", "品種", "生産地", "メモ") if fields.get(k)]
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": "中煎り",
            "roast_hint": "基本的に中煎りでお届け(焙煎度の指定可)",
            "flavor_notes": fields.get("フレバーノート") or fields.get("フレーバーノート"),
            "farm_note": " / ".join(farm_parts) or None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(pm.group(1).replace(",", "")),
            "weight_g": int(wm.group(1)) if wm else None,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kucoffee.json に出力しました")


if __name__ == "__main__":
    main()
