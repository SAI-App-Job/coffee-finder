# -*- coding: utf-8 -*-
"""
scrape_shiroganecoffee.py

白金珈琲(shirokane-coffee.jp、東京都港区高輪1-4-20の白金高輪店。運営は新宿区西新宿の
運営会社、実店舗は白金高輪店のみ)のオンラインショップの商品情報を取得する。
WordPress + Welcart(UTF-8)。豆はすべて「ご注文の都度焙煎」(受注焙煎)で、焙煎度は
注文時に選択する。

【住所について】
店舗ページ・特定商取引法表記(運営会社は東京都新宿区西新宿6-10-1)には白金高輪店の番地が
無いため、港区公式の食べきり協力店ページ(city.minato.tokyo.jp)で確認した
「港区高輪1-4-20」を採用した(2026-10)。

【対象商品について】
実データ確認済み(2026-10時点): 商品ジャンル「ブレンド豆」「ストレート豆」(3ページ)
「カフェインレス豆」「期間限定」の各一覧から商品URLの和集合を取り、豆の商品のみを
収録する。カップオンコーヒー・コールドブリュー(水出し)・ギフト・ラッピング・グッズ・
福袋は除外する。

【重量・価格・在庫】
詳細ページの「グラム」セレクト(100g〜500g、価格はg数に比例)の最小サイズ=100gと
その価格を採用する。在庫は最初のSKU(100g)の在庫表(table.sku-stock-table)の
「売り切れ」(tr.is-no-stock)で判定する。
"""

import json
import re
import unicodedata
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "白金珈琲",
    "url": "https://shirokane-coffee.jp/",
    "platform": "WordPress + Welcart",
    "address": "東京都港区高輪1-4-20",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://shirokane-coffee.jp"
GENRES = ["blend", "straight", "caffeine-less", "special"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("カップオン", "コールドブリュー", "水出し", "ギフト", "ラッピング", "福袋", "福豆", "セット", "グッズ", "パック")
MAX_PAGES = 6
ROAST_HINT = "注文時に焙煎度(ミディアム〜フレンチの4段階またはおまかせ)を選択(受注焙煎)"


def fetch(url: str) -> str | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for genre in GENRES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/item/itemgenre/{genre}/" + ("" if page == 1 else f"page/{page}/")
            html_text = fetch(url)
            if html_text is None:
                break
            soup = BeautifulSoup(html_text, "html.parser")
            new = 0
            for a in soup.select("a.itemlink"):
                name_el = a.select_one("span.itemname")
                if not name_el:
                    continue
                href = unquote(a["href"]).rstrip("/").lower()
                if href in items:
                    continue
                new += 1
                items[href] = {"name": re.sub(r"\s+", " ", name_el.get_text(strip=True)).strip(), "url": a["href"]}
            if new == 0:
                break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    weight_g = price = None
    sel = soup.select_one("select.custome-sku-select")
    if sel:
        rows = []
        for opt in sel.select("option"):
            m = re.match(r"^\s*(\d+)\s*g\s*[（(]\s*([\d,]+)\s*円", opt.get_text(strip=True))
            if m:
                rows.append((int(m.group(1)), int(m.group(2).replace(",", ""))))
        if rows:
            weight_g, price = min(rows)
    if price is None:
        unit = soup.select_one("#sku-unit-price")
        if unit:
            wm = re.search(r"(\d+)\s*g", unit.get_text())
            pm = soup.select_one("#sku-unit-price .sku-price")
            if wm and pm:
                weight_g = int(wm.group(1))
                price = int(pm.get_text(strip=True).replace(",", ""))
    stock_tr = soup.select_one("table.sku-stock-table tr")
    out_of_stock = bool(stock_tr and "is-no-stock" in (stock_tr.get("class") or []))
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    desc = ""
    if "商品説明" in lines:
        start = lines.index("商品説明") + 1
        end = next((i for i in range(start, len(lines)) if lines[i] == "おすすめ商品"), len(lines))
        desc = " ".join(lines[start:end])
    return {"weight_g": weight_g, "price": price, "out_of_stock": out_of_stock, "desc": desc}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    display = re.sub(r"\s*\d+\s*[gｇ]\s*$", "", unicodedata.normalize("NFKC", name)).strip()
    display = re.sub(r"\s+", " ", display)
    parsed = parse_product(display)
    if "ブレンド" in display or parsed["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, display)
        if display.startswith("タイ "):
            # 辞書は「タイ」を誤爆防止のため持たないので先頭語から補う
            parsed["origin_country"] = "タイ"
            parsed["origin_source"] = "raw_name"
        elif "ハワイコナ" in display:
            parsed["origin_country"] = "アメリカ(ハワイ)"
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            # 銘柄名のみで産地不明の場合は商品説明の冒頭の国名表記から補う
            country = detect_country_name(detail["desc"][:200])
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description"
    desc = detail["desc"]
    out = detail["out_of_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": ROAST_HINT,
        "flavor_notes": desc[:300] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            html_text = fetch(item["url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        if html_text is None:
            continue
        rec = build_record(item, parse_detail(html_text))
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_shiroganecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shiroganecoffee.json に出力しました")


if __name__ == "__main__":
    main()
