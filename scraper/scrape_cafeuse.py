# -*- coding: utf-8 -*-
"""
scrape_cafeuse.py

筋金珈琲焙煎所(元・自家焙煎珈琲豆屋cafeuse、cafeuse.com、東京都世田谷区北沢3-31-3、
下北沢)の商品情報を取得する。運営は有限会社オールド・マーケット。MakeShop(旧
shopbrand/shopdetail形式、EUC-JP)。店舗は下北沢の1店舗で自家焙煎。

【住所について】
特定商取引法表示・会社概要ページで「東京都世田谷区北沢3-31-3」と確認済み(2026-10)。
(渋谷区神宮前という情報は誤り。)

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「珈琲豆」(/shopbrand/ct9/、全22件、1ページ)
のうち、ブレンド・ストレート(SOB=スペシャルティ)の焙煎豆のみを対象とする。
ドリップバッグ(単品・5包・10包セット)・ギフトBOX(箱のみ)はNON_BEAN_KEYWORDSで除外。
「デカフェ・メキシコSOB」はカフェインレス豆のため対象(ストレート)。
「極上アイス珈琲ブレンド」はアイスコーヒー向けに配合した焙煎豆(ブレンド)のため対象。
商品名に容量表記(100g)が無い商品(コスタリカSOB・極上アイス珈琲ブレンド)は
ページ本文にも容量の記載が無いためweight_g=None(推測しない)。

【価格・在庫】
一覧ページの税込価格をそのまま採用。「品切れ」表示(p.soldout)があるものは完売。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "筋金珈琲焙煎所",
    "url": "https://cafeuse.com/",
    "platform": "MakeShop",
    "address": "東京都世田谷区北沢3-31-3",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://cafeuse.com"
LIST_URL = f"{BASE_URL}/shopbrand/ct9/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ("ドリップバッグ", "ギフト", "BOX", "セット")
ROAST_PATTERN = re.compile(r"(やや深煎り|中深煎り|浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def parse_list(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    for li in soup.select("ul.innerList li"):
        a = li.select_one("p.name a")
        if not a:
            continue
        m = re.search(r"/shopdetail/(\d+)/", a["href"])
        if not m:
            continue
        price_el = li.select_one("em.price")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        items.append({
            "id": m.group(1),
            "name": a.get_text(strip=True),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "out_of_stock": li.select_one("p.soldout") is not None,
        })
    return items


def parse_detail(html_text: str, name: str) -> list[str]:
    """商品名の次の行から「価格 :」の手前までを説明文の行リストとして返す。"""
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    end = next((i for i, ln in enumerate(lines) if ln.startswith("価格")), None)
    if end is None:
        return []
    start = None
    for i in range(end - 1, -1, -1):
        if lines[i] == name.strip() or lines[i] in ("前の商品", "次の商品"):
            start = i
            if lines[i] == name.strip():
                break
    if start is None:
        return []
    return [ln for ln in lines[start + 1:end] if ln not in ("前の商品", "次の商品")]


def extract_weight(name: str) -> int | None:
    m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", name), re.I)
    return int(m.group(1)) if m else None


def clean_name(name: str) -> str:
    n = re.sub(r"【\s*\d+\s*g\s*】", "", unicodedata.normalize("NFKC", name))
    n = re.sub(r"\s*\d+\s*g\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def build_record(item: dict, desc_lines: list[str]) -> dict | None:
    name = item["name"].strip()
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    display = clean_name(name)
    parsed = parse_product(display)
    is_blend = "ブレンド" in display or "ぶれんど" in display or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, display)

    desc = " ".join(desc_lines)
    flavor_notes = None
    for ln in desc_lines:
        if ln.startswith("味の感想"):
            flavor_notes = re.sub(r"^味の感想[\s　:：]*", "", ln)
            break
    if not flavor_notes and desc:
        flavor_notes = desc[:300]
    farm_bits = [ln for ln in desc_lines if re.match(r"^(生産地|農\s*地|品\s*種|精\s*製|標\s*高|生産者)", ln)]
    farm_note = " / ".join(re.sub(r"[\s　]+", " ", ln) for ln in farm_bits) or None
    rm = ROAST_PATTERN.search(desc)

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
        "roast_hint": rm.group(1) if rm else None,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": extract_weight(name),
        "stock_status": "完売" if item["out_of_stock"] else "販売中",
        "out_of_stock": item["out_of_stock"],
        "product_url": f"{BASE_URL}/shopdetail/{item['id']}/",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list(fetch(LIST_URL)):
        if any(kw in item["name"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            lines = parse_detail(fetch(f"{BASE_URL}/shopdetail/{item['id']}/"), item["name"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            lines = []
        rec = build_record(item, lines)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafeuse.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafeuse.json に出力しました")


if __name__ == "__main__":
    main()
