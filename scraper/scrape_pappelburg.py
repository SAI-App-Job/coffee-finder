# -*- coding: utf-8 -*-
"""
scrape_pappelburg.py

パペルブルグ(Pappelburg、burg-kaffee.com、東京都八王子市鑓水530-1、御殿山の自家焙煎コーヒー
店。ネットショップは「burg-kaffee」、店舗情報は pappelburg.com)の商品情報を取得する。
カラーミーショップ(charset=euc-jp、`resp.encoding = "euc-jp"`を明示)。店舗は1店舗。

【住所について】
ショップの特定商取引法に基づく表記の住所「東京都八王子市鑓水530-1」を採用(2026-10確認。
「柳城530-1」という情報は誤り)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(cbid=2473138、全39商品・4ページ。
Single Origin・Original Blend・限定ロット)のうち、「フレイヤ＆フレイ夏ブレンドセット」
(2種のセット)を除く38件。ドリップコーヒー・コーヒーベース・ギフト・Value Set・Whole Sale
(業務用)・クッキー・グッズ・御殿山チーズケーキは別カテゴリのため対象外。
2026-10時点で在庫なし(「売り切れ」)が14件あるが、現行掲載品として完売扱いで収録する。

【重量・価格・在庫】
詳細ページの「内容量」(100g/200g/500g/1kg、価格はグラム比例)のうち最小サイズ(通常100g)と
その税込価格を採用する。オプション表の無い限定ロットは、価格は一覧の税込価格、重量は
ページ内に記載が無いためNone。在庫は一覧の「売り切れ」表示で判定する。
パンくずの「Original Blend」所属の商品(ブルグ・レー・シュランゲ等のハウスブレンド)と、
名前に「ブレンド」を含む商品はブレンド扱い(産地None)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Pappelburg",
    "url": "https://burg-kaffee.com/",
    "platform": "カラーミーショップ",
    "address": "東京都八王子市鑓水530-1",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.burg-kaffee.com"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2473138&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "set ", "ギフト", "ドリップバッグ")
MAX_PAGES = 8
SIZE_ROW = re.compile(r"^(\d+(?:\.\d+)?)\s*(kg|g)$", re.I)


def fetch(url: str) -> str | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}&page={page}"
        html_text = fetch(url)
        if html_text is None:
            break
        soup = BeautifulSoup(html_text, "html.parser")
        new = 0
        for li in soup.select("li.c-item-list__item"):
            a = li.select_one(".c-item-list__ttl a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_el = li.select_one(".c-item-list__price")
            pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
            text = li.get_text(" ", strip=True)
            items[m.group(1)] = {
                "pid": m.group(1),
                "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": "売り切れ" in text or "SOLD OUT" in text,
            }
        if new == 0:
            break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    # パンくず(「コーヒー豆」の次の行)= Single Origin / Original Blend 等
    crumb = None
    for i in range(len(lines) - 2):
        if lines[i] == "TOP" and lines[i + 1] == "コーヒー豆":
            crumb = lines[i + 2]
            break
    # 「豆のまま」の直後の「100g / 700円(税52円)」の組
    rows = []
    if "豆のまま" in lines:
        i = lines.index("豆のまま") + 1
        while i + 1 < len(lines):
            m = SIZE_ROW.match(lines[i])
            pm = re.match(r"^([\d,]+)\s*円", lines[i + 1])
            if m and pm:
                w = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
                rows.append((int(w), int(pm.group(1).replace(",", ""))))
                i += 2
            else:
                break
    desc: list[str] = []
    if "Detail" in lines:
        start = lines.index("Detail") + 1
        sect = lines[start:start + 30]
        cut = next((i for i, ln in enumerate(sect) if ln.startswith(("Add To Cart", "ご利用ガイド"))), len(sect))
        desc = [
            ln for ln in sect[:cut]
            if not re.match(r"^\d+\s*k?g", ln, re.I)
            and not re.search(r"%\s*off|税抜", ln, re.I)
            and not ln.startswith(("基本情報", "商品名", "内容量", "挽き方"))
        ][:12]
    return {"crumb": crumb, "rows": rows, "desc": " ".join(desc)}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    low = name.lower()
    if any(kw in low for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", name)
    parsed = parse_product(norm)
    is_blend = detail["crumb"] == "Original Blend" or "ブレンド" in norm or "blend" in low
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, norm)
        if not parsed["origin_country"]:
            c = detect_country_name(norm)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "country_name"
    weight_g = None
    price = item["price"]
    if detail["rows"]:
        weight_g, price = min(detail["rows"], key=lambda r: r[0])
    out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": norm,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": (None if "※ご注文時にお選びください" in detail["desc"] else detail["desc"][:300]) or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"].lower() for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            html_text = fetch(f"{BASE_URL}/?pid={item['pid']}")
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        detail = parse_detail(html_text) if html_text else {"crumb": None, "rows": [], "desc": ""}
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_pappelburg.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pappelburg.json に出力しました")


if __name__ == "__main__":
    main()
