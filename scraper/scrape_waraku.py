# -*- coding: utf-8 -*-
"""
scrape_waraku.py

焙煎元 和樂(baisenmoto-waraku.com、香川県さぬき市志度365-9)の商品情報を取得する。
xaas3.jp系ASPカート(独自ドメイン)。

【住所】
実データ確認済み(2026-10-15): 店舗案内(/shop.html)・特定商取引法表記(/info.html、販売業者:
株式会社まこと)とも「〒769-2101 香川県さぬき市志度365-9」で一致。

【対象商品】
実データ確認済み: カテゴリ139「珈琲豆(ストレート、ブレンド)」(全22件、ページネーションなし)のうち、
単品豆6・ブレンド7・デカフェ3(予約受付中、10/22より順次発送)の16件を収録する。
全商品に100g入りがあり(ブレンド・単品は100g/400gの選択、デカフェは100gのみ)、一覧の
最小価格=100gの価格。商品名末尾の数字(商品通し番号)と焙煎度表記「(浅煎り)」等は取り除き、
焙煎度はroast_hintに入れる。
除外: お試しセット(100g×2種・40g×3種)、1kgセット(5種各200g)、「今週のお得なおすすめ豆」
(3日間限定で銘柄が毎週入れ替わり、焙煎度も購入時選択)、「今週のお得なおすすめ豆40g×3種類」(セット)、
カフェインレス・メキシコ1kg以上(オーダー焙煎、大容量のみ)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (apply_category_hint_fallback, detect_stock_status, parse_product)

SHOP_INFO = {
    "name": "焙煎元 和樂",
    "url": "https://www.baisenmoto-waraku.com/",
    "platform": "独自カート(xaas3.jp)",
    "address": "香川県さぬき市志度365-9",
    "prefecture": "香川県",
    "robots_txt_status": "許可(2026-10確認。User-Agent: * で/default/error/と/preview/のみDisallow)",
}

BASE_URL = "https://www.baisenmoto-waraku.com"
LIST_URL = f"{BASE_URL}/category/139/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5

EXCLUDE_RULES = [
    ("お試しセット", "セット(お試し)"),
    ("セット", "セット"),
    ("おすすめ豆", "週替わりの限定豆/セット(銘柄・焙煎度が毎週入れ替わる)"),
    ("１ｋｇ以上", "事業者向け大容量のみ(1kg以上オーダー焙煎)"),
    ("1kg以上", "事業者向け大容量のみ(1kg以上オーダー焙煎)"),
]
ROAST_PATTERN = re.compile(r"[（(]\s*((?:浅|中浅|中|中深|深)煎り)\s*[）)]")


def fetch(url: str) -> BeautifulSoup:
    # 502/503/429 などの一時的エラーは待機時間を伸ばして再試行する(回避ではなく間隔拡大)
    for attempt in range(5):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code in (429, 502, 503, 504) and attempt < 4:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        break
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def title_weight(title: str) -> int | None:
    m = re.search(r"(\d+)\s*g入り", unicodedata.normalize("NFKC", title))
    return int(m.group(1)) if m else None


def clean_name(title: str) -> tuple[str, str | None]:
    t = unicodedata.normalize("NFKC", title).replace("~", "～")
    t = re.sub(r"【[^】]*】", " ", t)           # 【新登場】【※ご予約受付中※…】【JAS認証…】
    t = re.sub(r"/\s*100g入り", " ", t)
    roast = None
    m = ROAST_PATTERN.search(t)
    if m:
        roast = m.group(1)
        t = ROAST_PATTERN.sub(" ", t)
    t = re.sub(r"\s+\d+\s*$", "", t.strip())     # 末尾の商品通し番号
    return re.sub(r"\s+", " ", t).strip(), roast


def detail(url: str) -> dict:
    soup = fetch(url)
    box = soup.select_one("#itemDetail01")
    stock_el = box.select_one("li.stock1 p.data")
    stock_txt = stock_el.get_text(strip=True) if stock_el else ""
    weights = []
    for sel in box.select("select"):
        for o in sel.select("option"):
            m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", o.get_text()))
            if m:
                weights.append(int(m.group(1)))
    desc = None
    first = box.select_one("div.inner")
    if first:
        lines = [ln for ln in first.get_text("\n", strip=True).split("\n")]
        keep = []
        for ln in lines:
            if ln.startswith("■"):
                break
            if keep and keep[-1] == ln:   # 見出しと本文の重複行を除く
                continue
            keep.append(ln)
        desc = re.sub(r"\s+", " ", " ".join(keep)).strip() or None
    return {"out_of_stock": "在庫切れ" in stock_txt, "weight_g": min(weights) if weights else None, "desc": desc}


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    soup = fetch(LIST_URL)
    records, excluded = [], []
    for li in soup.select("ul.itemList > li"):
        a = li.select_one("p.name a")
        if not a:
            continue
        title, href = a.get_text(strip=True), a["href"]
        price_el = li.select_one("p.price")
        price_m = re.search(r"([\d,]+)円", price_el.get_text()) if price_el else None
        price = int(price_m.group(1).replace(",", "")) if price_m else None
        norm_title = unicodedata.normalize("NFKC", title)
        reason = next((r for kw, r in EXCLUDE_RULES
                       if kw in title or kw in norm_title), None)
        if reason:
            excluded.append({"raw_name": title, "product_url": href, "reason": reason})
            continue
        name, roast = clean_name(title)
        time.sleep(CRAWL_DELAY_SECONDS)
        d = detail(href)
        parsed = parse_product(name)
        is_decaf = "カフェインレス" in name
        parsed = apply_category_hint_fallback(parsed, None)
        stock_status = detect_stock_status(title, d["out_of_stock"])
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "デカフェ" if is_decaf else parsed["category"],
            "origin_country": None if parsed["category"] == "ブレンド" else parsed["origin_country"],
            "origin_source": None if parsed["category"] == "ブレンド" else parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast,
            "flavor_notes": None if is_decaf else d["desc"],
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": d["weight_g"] or title_weight(title),
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": href,
        })
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    with open("data_waraku.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records, "excluded_products": excluded},
                  f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_waraku.json に出力しました(除外{len(excluded)}件)")
