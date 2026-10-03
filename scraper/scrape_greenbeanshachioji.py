# -*- coding: utf-8 -*-
"""
scrape_greenbeanshachioji.py

グリーンビーンズ(greenbeans-shop.com、東京都八王子市大塚621-1-102 神尾ビル、
注文を頂いてから焙煎する自家焙煎店。生豆・焙煎後ともに手作業で1粒ずつ選別)の
商品情報を取得する。Jimdo(ショップ機能は使わず、カテゴリページ上の静的な価格表)。
神奈川県川崎市の別店舗「Green Beans」(green-beans9669.com)とは別店舗。

【ページ構造について】
実データ確認済み(2026-10時点): 商品カテゴリページ(ストレート6ページ・ブレンド2ページ)は
個別商品ページを持たず、「銘柄名→甘み/酸味/苦味の○△表記→説明文→『200g ￥1200』」の
並びで商品が列挙される。全商品が200g単一サイズのため、その200gを代表重量・価格とする。
銘柄名に「(完売)」が付くものは完売扱いとし、名称から取り除く。「ニューギニア
トロピカルマウンテン」は中南米１と大洋州の両ページに重複掲載されているため1件に
統合する(産地はニューギニア=パプアニューギニアのため大洋州側を採用)。
ギフト・セット、器具類は対象外。個別URLが無いため product_url は
カテゴリページURL + '#' + 商品名とする。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "グリーンビーンズ(八王子)",
    "url": "https://www.greenbeans-shop.com/",
    "platform": "Jimdo(静的価格表)",
    "address": "東京都八王子市大塚621-1-102 神尾ビル",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.greenbeans-shop.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (カテゴリページのパス, カテゴリ見出し)
CATEGORY_PAGES = [
    ("/商-品/ストレート/大洋州/", "大洋州"),
    ("/商-品/ストレート/中南米１/", "中南米１"),
    ("/商-品/ストレート/中南米２/", "中南米２"),
    ("/商-品/ストレート/アジア/", "アジア"),
    ("/商-品/ストレート/アフリカ/", "アフリカ"),
    ("/商-品/ストレート/中東/", "中東"),
    ("/商-品/ブレンド１/", "ブレンド１"),
    ("/商-品/ブレンド２/", "ブレンド２"),
]

# 銘柄名・説明から産地が判別できないもの(説明文の産地記載による)
ORIGIN_OVERRIDES = {
    "インカ(オーガニック)": "ペルー",
    "マヤ(オーガニック)": "メキシコ",
    "ニューギニアトロピカルマウンテン": "パプアニューギニア",
    "モカイルガチェフェ": "エチオピア",
    "モカマタリ": "イエメン",
    "トラジャ": "インドネシア",
    "マンデリン": "インドネシア",
    "インドプランテーション": "インド",
    "キリマンジャロタンザニア": "タンザニア",
}

PRICE_PATTERN = re.compile(r"^(\d+)g\s*[¥￥]\s*([\d,]+)$")


def norm(text: str) -> str:
    """全角英数・括弧を半角に正規化し、空白を整理する。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def parse_page(path: str, heading: str) -> list[dict]:
    url = BASE_URL + quote(path)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    lines = [ln.strip() for ln in BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True).split("\n") if ln.strip()]
    # 本文: ページ見出し(カテゴリ名。メニューにも同名があるため最後の出現)〜「返金条件と返品取消申請書」の手前
    start = max(i for i, ln in enumerate(lines) if ln == heading) + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("返金条件"))
    body = lines[start:end]

    items = []
    cur = None
    for ln in body:
        n = norm(ln)
        m = PRICE_PATTERN.match(n)
        if m and cur is not None:
            cur["weight_g"] = int(m.group(1))
            cur["price"] = int(m.group(2).replace(",", ""))
            items.append(cur)
            cur = None
            continue
        if cur is None:
            cur = {"name": n, "desc": []}
        else:
            cur["desc"].append(n)
    for it in items:
        it["page_url"] = url
    return items


def build_record(item: dict) -> dict:
    raw = item["name"]
    out_of_stock = "完売" in raw
    name = norm(re.sub(r"[(（]完売[)）]", "", raw))
    taste_line = next((d for d in item["desc"] if d.startswith("甘み")), None)
    desc_lines = [d for d in item["desc"] if not d.startswith("甘み")]
    desc = " ".join(desc_lines)
    notes = " ".join(x for x in (taste_line, desc) if x) or None

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = ORIGIN_OVERRIDES.get(name) or next((v for k, v in ORIGIN_OVERRIDES.items() if name.startswith(k)), None)
        if not parsed["origin_country"]:
            country = override or detect_country_name(desc)
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description"

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
        "flavor_notes": notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": item["page_url"] + "#" + quote(name),
    }


def scrape_all_products() -> list[dict]:
    records = []
    seen = set()
    for path, heading in CATEGORY_PAGES:
        try:
            items = parse_page(path, heading)
        except (requests.RequestException, ValueError, StopIteration) as e:
            print(f"[warn] ページ取得/解析失敗: {path} ({e})")
            continue
        for it in items:
            rec = build_record(it)
            key = rec["raw_name"]
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_greenbeanshachioji.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_greenbeanshachioji.json に出力しました")


if __name__ == "__main__":
    main()
