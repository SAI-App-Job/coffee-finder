# -*- coding: utf-8 -*-
"""
scrape_globecoffee.py

GLOBE COFFEE(グローブコーヒー、globecoffee.tokyo、東京都品川区小山5-25-10 平岡マンション1B、
目黒線・西小山駅徒歩5分、店内に焙煎機を持つ自家焙煎のコーヒー豆専門店・カフェ)の商品情報を
取得する。カラーミーショップ(charset=euc-jp、`resp.encoding = "euc-jp"`を明示)。

【住所について】
公式サイトのフッター・ご利用ガイドに「東京都品川区小山5-25-10 平岡マンション 1B」
(渋谷区神宮前という情報は誤り。2026-10確認)。トップページのmeta descriptionに
「西小山の自家焙煎コーヒー豆専門店」「焙煎したての豆を全国へ」と明記されている。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(cbid=2149593、全13商品・2ページ)
を対象とする(ブレンド5・季節ブレンド1(ルスカ)・サマーナイト(完売)・ストレート6・
ノンカフェイン(デカフェ)1)。「[初回限定]お試しセット」「ドリップバッグコーヒー」
「コーヒー器具・グッズ」「ギフト」は別カテゴリのため対象外。

【重量・価格・在庫】
すべて商品名の「200g」(1サイズのみ)。価格は詳細ページの「価格 N円(内税)」。
一覧で「SOLD OUT」表示(is-soldout)のものは完売(サマーナイトは完売時も詳細ページに
価格が残っているためその価格を採用)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GLOBE COFFEE",
    "url": "https://globecoffee.tokyo/",
    "platform": "カラーミーショップ",
    "address": "東京都品川区小山5-25-10 平岡マンション1B",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://globecoffee.tokyo"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2149593&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップバッグ", "お試し", "セット", "ギフト")
MAX_PAGES = 5


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}&page={page}"
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for card in soup.select("article.card"):
            a = card.select_one("h3.item-name a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_el = card.select_one(".item-price")
            sold = bool(price_el and "is-soldout" in (price_el.get("class") or []))
            exp = card.select_one(".item-exp-sort")
            items[m.group(1)] = {
                "pid": m.group(1),
                "name": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "short": exp.get_text(strip=True) if exp else None,
                "sold_out": sold,
            }
        if new == 0:
            break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    price = None
    desc_lines: list[str] = []
    farm_lines: list[str] = []
    # 商品名が3回続いた直後に「N円(内税)」、その後に説明文
    idx = next((i for i, ln in enumerate(lines) if re.match(r"^[\d,]+円\(内税\)$", ln)), None)
    if idx is not None:
        price = int(re.match(r"^([\d,]+)円", lines[idx]).group(1).replace(",", ""))
        section = "desc"
        for ln in lines[idx + 1:]:
            if ln == "価格":
                break
            if ln.startswith("□"):
                section = "farm" if "トレーサビリティ" in ln else "skip"
                continue
            if section == "desc":
                desc_lines.append(ln)
            elif section == "farm":
                farm_lines.append(ln)
    return {"price": price, "desc": " ".join(desc_lines), "farm": " / ".join(farm_lines)}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", name)
    wm = re.search(r"(\d+)\s*g\b", norm)
    weight_g = int(wm.group(1)) if wm else None
    parsed = parse_product(norm)
    if "ブレンド" in norm or parsed["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, norm)
    desc = detail["desc"]
    flavor_notes = " ".join(x for x in (item["short"], desc) if x)[:300] or None
    out = item["sold_out"]
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
        "flavor_notes": flavor_notes,
        "farm_note": detail["farm"] or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/?pid={item['pid']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_globecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_globecoffee.json に出力しました")


if __name__ == "__main__":
    main()
