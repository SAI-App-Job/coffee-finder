# -*- coding: utf-8 -*-
"""
scrape_cafederyuban.py

Cafe de Ryuban(カフェ・ド・リュウバン、cafederyuban.com、宮城県仙台市青葉区広瀬町4-27)の
商品情報を取得する。独自カート(Yii製)。

【取得方法】
実データ確認済み(2026-10時点): `/shop/Coffee`(コーヒー豆カテゴリ)に全商品が1ページで並び、
商品ごとに `/shop/Blend/<id>` `/shop/Straight/<id>` の個別ページがある(ページネーション無し)。
一覧カードから名前・焙煎度・内容量・税込価格を取り、個別ページからカートボタンの有無と
商品紹介文を取得する。HTMLのエンコーディングは行ごとにUTF-8とShift_JISが混在するため、
行単位でUTF-8を試してから cp932 にフォールバックして復号する。

全商品が200gのみ(100g設定なし)のため、200gを代表とする。同一銘柄が焙煎度違いで別商品
(別ID)として並ぶ(例: コロンビア/サンタ・フェの深煎り・やや深煎り・中煎り)ので、
重複する名称には焙煎度を括弧書きで付けて区別する。カップオン(ドリップバッグ類)・リキッド・
ギフト・雑貨のカテゴリは対象外(/shop/Coffee のみ取得)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Cafe de Ryuban",
    "url": "https://www.cafederyuban.com/",
    "platform": "独自カート",
    "address": "宮城県仙台市青葉区広瀬町4-27",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.cafederyuban.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

CARD_PATTERN = re.compile(
    r'<a href="https://www\.cafederyuban\.com/shop/(Blend|Straight)/(\d+)">\s*<h6[^>]*><b>(.*?)</b>.*?'
    r'<p class="card-text mb-0">(.*?)</p>\s*<p class="card-text text-right mt-0">\s*<b>(.*?)</b>',
    re.S,
)


def decode_mixed(raw: bytes) -> str:
    lines = []
    for line in raw.split(b"\n"):
        try:
            lines.append(line.decode("utf-8"))
        except UnicodeDecodeError:
            lines.append(line.decode("cp932", errors="replace"))
    return "\n".join(lines)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return decode_mixed(resp.content)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("&nbsp;", " ")).strip()


def scrape_all_products() -> list[dict]:
    html = fetch(f"{BASE_URL}/shop/Coffee")
    cards = []
    for m in CARD_PATTERN.finditer(html):
        kind, pid, name, meta, price_text = m.groups()
        name = clean(BeautifulSoup(name, "html.parser").get_text())
        meta_text = clean(BeautifulSoup(meta, "html.parser").get_text(" "))
        wm = re.search(r"(\d+)\s*g", meta_text)
        roast = clean(meta_text[:wm.start()]) if wm else None
        pm = re.search(r"([\d,]+)\s*円", price_text)
        cards.append({
            "kind": kind, "id": pid, "name": name, "roast": roast or None,
            "weight": int(wm.group(1)) if wm else None,
            "price": int(pm.group(1).replace(",", "")) if pm else None,
        })

    name_count = {}
    for c in cards:
        name_count[c["name"]] = name_count.get(c["name"], 0) + 1

    records = []
    for c in cards:
        url = f"{BASE_URL}/shop/{c['kind']}/{c['id']}"
        detail = fetch(url)
        soup = BeautifulSoup(detail, "html.parser")
        available = soup.find(id="cartBtn") is not None
        desc = None
        for h5 in soup.find_all("h5"):
            if "商品のご紹介" in h5.get_text():
                p = h5.find_next("p")
                if p:
                    desc = clean(p.get_text(" "))[:400] or None
                break

        raw_name = c["name"]
        if name_count[c["name"]] > 1 and c["roast"]:
            raw_name = f"{raw_name}({c['roast']})"

        parsed = parse_product(raw_name)
        if c["kind"] == "Blend" or "ブレンド" in raw_name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(raw_name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, raw_name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": c["roast"],
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": c["price"],
            "weight_g": c["weight"],
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafederyuban.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafederyuban.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
